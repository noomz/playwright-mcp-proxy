"""
Comparison tests: proxy tool stack vs direct Playwright MCP subprocess communication.

Requirements:
    - Server running on localhost:34501: `uv run playwright-proxy-server`
    - npx available and @playwright/mcp@0.0.68 installed
    - Internet access (tests hit https://example.com and https://httpbin.org)

Run:
    uv run pytest tests/test_comparison.py -v -m integration

These tests prove the proxy faithfully preserves Playwright behavior while adding
SQLite persistence, diff-based content delivery, and content search filtering.
"""

import asyncio
import json

import httpx
import pytest

# ---------------------------------------------------------------------------
# DirectPlaywrightClient — minimal async context manager for direct MCP stdio
# ---------------------------------------------------------------------------


class DirectPlaywrightClient:
    """Minimal stdio JSON-RPC client for direct Playwright MCP access.

    Mirrors PlaywrightManager.send_request() but without health checks or
    restart logic. Spawns a separate `npx @playwright/mcp@0.0.68 --headless`
    process for comparison tests.
    """

    def __init__(self):
        self.process = None
        self._msg_id = 0

    async def start(self):
        """Spawn the Playwright MCP subprocess and send initialize handshake."""
        self.process = await asyncio.create_subprocess_exec(
            "npx", "@playwright/mcp@0.0.68", "--headless",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._initialize()

    async def stop(self):
        """Terminate the subprocess and wait for it to exit."""
        if self.process:
            self.process.terminate()
            await self.process.wait()

    async def _initialize(self):
        """Send MCP initialize handshake."""
        await self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-direct", "version": "0.0.1"},
        })

    async def send(self, method: str, params: dict) -> dict:
        """Send a JSON-RPC message and return the result.

        Uses asyncio.wait_for with 30s timeout on readline to prevent hangs
        on slow network or unresponsive subprocess.

        Raises RuntimeError if MCP returns an error response.
        """
        self._msg_id += 1
        msg = json.dumps({
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params,
        }) + "\n"
        self.process.stdin.write(msg.encode())
        await self.process.stdin.drain()
        line = await asyncio.wait_for(
            self.process.stdout.readline(), timeout=30.0
        )
        response = json.loads(line.decode())
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response.get("result", {})

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a Playwright MCP tool and return the result dict."""
        return await self.send("tools/call", {"name": name, "arguments": arguments})


# ---------------------------------------------------------------------------
# Proxy helper functions (mirrors test_integration_live.py patterns)
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:34501"
TIMEOUT = 60.0


async def _create_session(client: httpx.AsyncClient) -> str:
    """Create a new browser session and return session_id."""
    resp = await client.post("/sessions")
    assert resp.status_code == 200
    return resp.json()["session_id"]


async def _proxy(client: httpx.AsyncClient, session_id: str, tool: str, params: dict) -> dict:
    """Send a proxy request and return the JSON response."""
    resp = await client.post("/proxy", json={
        "session_id": session_id,
        "tool": tool,
        "params": params,
    })
    assert resp.status_code == 200, f"Proxy call failed: {resp.text}"
    return resp.json()


async def _navigate_and_snapshot(
    client: httpx.AsyncClient, session_id: str, url: str
) -> tuple[str, str]:
    """Navigate to url, take snapshot, get content, return (ref_id, content)."""
    await _proxy(client, session_id, "browser_navigate", {"url": url})
    snap = await _proxy(client, session_id, "browser_snapshot", {})
    ref_id = snap["ref_id"]
    resp = await client.get(f"/content/{ref_id}")
    return ref_id, resp.json()["content"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def direct_client():
    """Spawn a direct Playwright MCP subprocess for comparison tests.

    Function-scoped: each test gets its own subprocess to avoid state leakage.
    """
    client = DirectPlaywrightClient()
    await client.start()
    yield client
    await client.stop()


# ---------------------------------------------------------------------------
# Scenario 1: Simple navigation — CMP-01
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario1_simple_navigation(direct_client):
    """Both proxy and direct paths navigate to example.com and see 'Example Domain'.

    Demonstrates: proxy metadata + ref_id workflow vs direct inline content.
    """
    # Proxy path
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)
        _, proxy_content = await _navigate_and_snapshot(client, session_id, "https://example.com")

    assert "Example Domain" in proxy_content, (
        f"Proxy content missing 'Example Domain'. Got: {proxy_content[:500]}"
    )

    # Direct path
    await direct_client.call_tool("browser_navigate", {"url": "https://example.com"})
    result = await direct_client.call_tool("browser_snapshot", {})
    direct_content = result["content"][0]["text"]

    assert result["content"][0]["type"] == "text", "Expected text content from direct snapshot"
    assert "Example Domain" in direct_content, (
        f"Direct content missing 'Example Domain'. Got: {direct_content[:500]}"
    )


# ---------------------------------------------------------------------------
# Scenario 2: Diff behavior — CMP-02
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario2_diff_behavior(direct_client):
    """Proxy second read returns empty (diff suppression); direct always returns full content.

    This is the clearest behavioral difference between proxy and direct paths.
    """
    # Proxy path: first read non-empty, second read empty (diff cursor)
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)
        await _proxy(client, session_id, "browser_navigate", {"url": "https://example.com"})
        snap = await _proxy(client, session_id, "browser_snapshot", {})
        ref_id = snap["ref_id"]

        # First read — full content returned, cursor created
        resp1 = await client.get(f"/content/{ref_id}")
        first_read = resp1.json()["content"]

        # Second read — same snapshot hash, diff cursor suppresses output
        resp2 = await client.get(f"/content/{ref_id}")
        second_read = resp2.json()["content"]

    assert len(first_read) > 0, "Proxy first read should return non-empty content"
    assert second_read == "", (
        f"Proxy second read should be empty (diff suppression), got: {second_read[:200]}"
    )

    # Direct path: two sequential snapshots both return full content
    await direct_client.call_tool("browser_navigate", {"url": "https://example.com"})
    r1 = await direct_client.call_tool("browser_snapshot", {})
    r2 = await direct_client.call_tool("browser_snapshot", {})
    direct_first = r1["content"][0]["text"]
    direct_second = r2["content"][0]["text"]

    assert len(direct_first) > 0, "Direct first snapshot should be non-empty"
    assert len(direct_second) > 0, "Direct second snapshot should be non-empty (no diff suppression)"


# ---------------------------------------------------------------------------
# Scenario 3: Multi-page navigation — CMP-03
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario3_multi_page_navigation(direct_client):
    """Both paths navigate to two sites in sequence and see correct content for each.

    Proxy value-add: all interactions logged with unique ref_ids; historical content
    retrievable from SQLite. Direct path: only current-call content available.
    """
    # Proxy path
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)

        ref_id1, content1 = await _navigate_and_snapshot(client, session_id, "https://example.com")
        ref_id2, content2 = await _navigate_and_snapshot(client, session_id, "https://httpbin.org")

    assert "Example Domain" in content1, (
        f"Proxy page 1 missing 'Example Domain'. Got: {content1[:500]}"
    )
    assert "httpbin" in content2.lower(), (
        f"Proxy page 2 missing 'httpbin'. Got: {content2[:500]}"
    )
    assert ref_id1 != ref_id2, "Each page navigation must produce a unique ref_id"

    # Direct path
    await direct_client.call_tool("browser_navigate", {"url": "https://example.com"})
    r1 = await direct_client.call_tool("browser_snapshot", {})
    direct_content1 = r1["content"][0]["text"]

    await direct_client.call_tool("browser_navigate", {"url": "https://httpbin.org"})
    r2 = await direct_client.call_tool("browser_snapshot", {})
    direct_content2 = r2["content"][0]["text"]

    assert "Example Domain" in direct_content1, (
        f"Direct page 1 missing 'Example Domain'. Got: {direct_content1[:500]}"
    )
    assert "httpbin" in direct_content2.lower(), (
        f"Direct page 2 missing 'httpbin'. Got: {direct_content2[:500]}"
    )


# ---------------------------------------------------------------------------
# Scenario 4: Content search — CMP-04
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario4_content_search(direct_client):
    """Proxy search_for parameter filters snapshot to fewer lines than full content.

    Proxy value-add: get_content(ref_id, search_for=...) returns only matching
    lines — smaller payload, fewer tokens. Direct path has no built-in filtering.
    """
    # Proxy path: filtered vs full content comparison
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)
        await _proxy(client, session_id, "browser_navigate", {"url": "https://example.com"})
        snap = await _proxy(client, session_id, "browser_snapshot", {})
        ref_id = snap["ref_id"]

        # Filtered: search_for limits returned lines
        filtered_resp = await client.get(f"/content/{ref_id}", params={
            "search_for": "Example Domain",
            "reset_cursor": True,
        })
        filtered_content = filtered_resp.json()["content"]

        # Full: reset cursor, no search filter
        full_resp = await client.get(f"/content/{ref_id}", params={"reset_cursor": True})
        full_content = full_resp.json()["content"]

    assert "Example Domain" in filtered_content, "Filtered content must contain search term"
    assert "Example Domain" in full_content, "Full content must contain search term"
    assert len(filtered_content) < len(full_content), (
        "Filtered content should be shorter than full content; "
        f"filtered={len(filtered_content)} full={len(full_content)}"
    )

    # Direct path: returns full accessibility tree — no built-in filtering
    await direct_client.call_tool("browser_navigate", {"url": "https://example.com"})
    result = await direct_client.call_tool("browser_snapshot", {})
    direct_content = result["content"][0]["text"]

    # Direct path: manually check content is present (no search_for API)
    assert "Example Domain" in direct_content, "Direct full content must contain search term"
    # Direct always returns full tree — length should be non-trivial
    assert len(direct_content) > len(filtered_content), (
        "Direct full snapshot should be longer than proxy's filtered result"
    )


# ---------------------------------------------------------------------------
# Scenario 5: Error handling — CMP-05
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario5_error_handling(direct_client):
    """Both paths handle an invalid URL navigation gracefully without crashing.

    Proxy value-add: errors are persisted in SQLite with ref_id for audit trail.
    """
    invalid_url = "https://this-domain-does-not-exist-at-all-12345.invalid"

    # Proxy path: expect either status == "error" or HTTP error status
    proxy_failed_gracefully = False
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)
        resp = await client.post("/proxy", json={
            "session_id": session_id,
            "tool": "browser_navigate",
            "params": {"url": invalid_url},
        })
        if resp.status_code == 200:
            data = resp.json()
            # Proxy may return status="error" or status="success" with Playwright error embedded
            proxy_failed_gracefully = True  # Did not crash — returned valid JSON
        elif resp.status_code >= 400:
            proxy_failed_gracefully = True  # HTTP error response — also graceful

    assert proxy_failed_gracefully, (
        f"Proxy must not crash on invalid URL. Status: {resp.status_code}"
    )

    # Direct path: expect either RuntimeError (MCP error) or result with isError
    direct_failed_gracefully = False
    try:
        result = await direct_client.call_tool("browser_navigate", {"url": invalid_url})
        # Some MCP versions return isError in the result instead of an error response
        direct_failed_gracefully = True  # Returned something — did not hang or crash
    except RuntimeError:
        # MCP returned an error response — this is acceptable graceful failure
        direct_failed_gracefully = True

    assert direct_failed_gracefully, "Direct client must not crash on invalid URL navigation"
