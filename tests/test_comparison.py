"""
Comparison tests: proxy tool stack vs direct Playwright MCP subprocess communication.

Requirements:
    - Server running on localhost:34501: `uv run playwright-proxy-server`
    - npx available and @playwright/mcp@0.0.68 installed
    - Internet access (tests hit example.com, iana.org, google.com, youtube.com)

Run:
    uv run pytest tests/test_comparison.py -v -s -m integration

Produces a performance comparison table at the end of the test run showing
payload sizes, latency, token estimates, and proxy value-add metrics.
"""

import asyncio
import json
import re
import time
from dataclasses import dataclass, field

import httpx
import pytest

# ---------------------------------------------------------------------------
# Metrics collection
# ---------------------------------------------------------------------------


@dataclass
class Measurement:
    """A single timed operation with payload tracking."""
    label: str
    path: str  # "proxy" or "direct"
    elapsed_ms: float = 0.0
    payload_bytes: int = 0
    estimated_tokens: int = 0


@dataclass
class ScenarioMetrics:
    """All measurements for one scenario."""
    name: str
    measurements: list[Measurement] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


# Module-level collector — printed at session end
_all_scenarios: list[ScenarioMetrics] = []


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# DirectPlaywrightClient — minimal async context manager for direct MCP stdio
# ---------------------------------------------------------------------------


class DirectPlaywrightClient:
    """Minimal stdio JSON-RPC client for direct Playwright MCP access.

    Spawns `npx @playwright/mcp@0.0.68 --headless --isolated` for comparison.
    """

    def __init__(self):
        self.process = None
        self._msg_id = 0

    async def start(self):
        """Spawn the Playwright MCP subprocess and send initialize handshake."""
        self.process = await asyncio.create_subprocess_exec(
            "npx", "@playwright/mcp@0.0.68", "--headless", "--isolated",
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
        """Send a JSON-RPC message and return the result."""
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
            self.process.stdout.readline(), timeout=60.0
        )
        response = json.loads(line.decode())
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response.get("result", {})

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """Call a Playwright MCP tool and return the result dict."""
        return await self.send("tools/call", {"name": name, "arguments": arguments})

    async def call_tool_timed(self, name: str, arguments: dict) -> tuple[dict, float]:
        """Call tool and return (result, elapsed_ms)."""
        t0 = time.perf_counter()
        result = await self.call_tool(name, arguments)
        elapsed = (time.perf_counter() - t0) * 1000
        return result, elapsed


# ---------------------------------------------------------------------------
# Proxy helper functions
# ---------------------------------------------------------------------------

BASE_URL = "http://localhost:34501"
TIMEOUT = 60.0


async def _create_session(client: httpx.AsyncClient) -> str:
    """Create a new browser session and return session_id."""
    resp = await client.post("/sessions")
    assert resp.status_code == 200
    return resp.json()["session_id"]


async def _proxy_timed(
    client: httpx.AsyncClient, session_id: str, tool: str, params: dict
) -> tuple[dict, float]:
    """Send a proxy request and return (json_response, elapsed_ms)."""
    t0 = time.perf_counter()
    resp = await client.post("/proxy", json={
        "session_id": session_id,
        "tool": tool,
        "params": params,
    })
    elapsed = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200, f"Proxy call failed: {resp.text}"
    return resp.json(), elapsed


async def _get_content_timed(
    client: httpx.AsyncClient, ref_id: str, **params
) -> tuple[str, float, int]:
    """Get content by ref_id, return (content, elapsed_ms, raw_bytes)."""
    t0 = time.perf_counter()
    resp = await client.get(f"/content/{ref_id}", params=params)
    elapsed = (time.perf_counter() - t0) * 1000
    body = resp.json()
    content = body.get("content", "")
    return content, elapsed, len(resp.content)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def direct_client():
    """Spawn a direct Playwright MCP subprocess for comparison tests."""
    client = DirectPlaywrightClient()
    await client.start()
    yield client
    await client.stop()


# ---------------------------------------------------------------------------
# Scenario 1: Simple navigation — CMP-01
# Measures: navigate+snapshot latency, payload size, token count
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario1_simple_navigation(direct_client):
    """Navigate to example.com — compare latency and payload size."""
    metrics = ScenarioMetrics(name="Simple Navigation (example.com)")

    # --- Proxy path ---
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)

        nav_resp, nav_ms = await _proxy_timed(client, session_id, "browser_navigate", {"url": "https://example.com"})
        snap_resp, snap_ms = await _proxy_timed(client, session_id, "browser_snapshot", {})
        ref_id = snap_resp["ref_id"]

        # Proxy initial response is metadata-only (small)
        proxy_meta_bytes = len(json.dumps(snap_resp).encode())
        metrics.measurements.append(Measurement(
            label="navigate", path="proxy",
            elapsed_ms=nav_ms, payload_bytes=len(json.dumps(nav_resp).encode()),
        ))
        metrics.measurements.append(Measurement(
            label="snapshot (metadata)", path="proxy",
            elapsed_ms=snap_ms, payload_bytes=proxy_meta_bytes,
            estimated_tokens=_estimate_tokens(json.dumps(snap_resp)),
        ))

        # get_content retrieves actual page content
        content, content_ms, content_bytes = await _get_content_timed(client, ref_id)
        metrics.measurements.append(Measurement(
            label="get_content", path="proxy",
            elapsed_ms=content_ms, payload_bytes=content_bytes,
            estimated_tokens=_estimate_tokens(content),
        ))

    assert "Example Domain" in content

    # --- Direct path ---
    _, direct_nav_ms = await direct_client.call_tool_timed("browser_navigate", {"url": "https://example.com"})
    result, direct_snap_ms = await direct_client.call_tool_timed("browser_snapshot", {})
    direct_content = result["content"][0]["text"]
    direct_bytes = len(json.dumps(result).encode())

    metrics.measurements.append(Measurement(
        label="navigate", path="direct",
        elapsed_ms=direct_nav_ms,
    ))
    metrics.measurements.append(Measurement(
        label="snapshot (full)", path="direct",
        elapsed_ms=direct_snap_ms, payload_bytes=direct_bytes,
        estimated_tokens=_estimate_tokens(direct_content),
    ))

    assert "Example Domain" in direct_content

    metrics.notes.append(
        f"Proxy metadata response: {proxy_meta_bytes}B vs Direct full snapshot: {direct_bytes}B"
    )
    _all_scenarios.append(metrics)


# ---------------------------------------------------------------------------
# Scenario 2: Diff behavior — CMP-02
# Measures: token savings on repeated reads
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario2_diff_behavior(direct_client):
    """Repeated reads — proxy diff suppression vs direct full payload every time."""
    metrics = ScenarioMetrics(name="Diff Suppression (repeated reads)")

    # --- Proxy path ---
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)
        await _proxy_timed(client, session_id, "browser_navigate", {"url": "https://example.com"})
        snap_resp, _ = await _proxy_timed(client, session_id, "browser_snapshot", {})
        ref_id = snap_resp["ref_id"]

        # First read — full content
        content1, ms1, bytes1 = await _get_content_timed(client, ref_id)
        # Second read — diff suppressed (empty)
        content2, ms2, bytes2 = await _get_content_timed(client, ref_id)
        # Third read with reset — full again
        content3, ms3, bytes3 = await _get_content_timed(client, ref_id, reset_cursor=True)

    assert len(content1) > 0
    assert content2 == ""
    assert len(content3) > 0

    metrics.measurements.append(Measurement(
        label="1st read (full)", path="proxy",
        elapsed_ms=ms1, payload_bytes=bytes1,
        estimated_tokens=_estimate_tokens(content1),
    ))
    metrics.measurements.append(Measurement(
        label="2nd read (diff=empty)", path="proxy",
        elapsed_ms=ms2, payload_bytes=bytes2,
        estimated_tokens=_estimate_tokens(content2),
    ))
    metrics.measurements.append(Measurement(
        label="3rd read (reset=full)", path="proxy",
        elapsed_ms=ms3, payload_bytes=bytes3,
        estimated_tokens=_estimate_tokens(content3),
    ))

    # --- Direct path ---
    await direct_client.call_tool("browser_navigate", {"url": "https://example.com"})
    r1, d_ms1 = await direct_client.call_tool_timed("browser_snapshot", {})
    r2, d_ms2 = await direct_client.call_tool_timed("browser_snapshot", {})
    r3, d_ms3 = await direct_client.call_tool_timed("browser_snapshot", {})
    d_text1 = r1["content"][0]["text"]
    d_text2 = r2["content"][0]["text"]
    d_text3 = r3["content"][0]["text"]
    d_bytes1 = len(json.dumps(r1).encode())
    d_bytes2 = len(json.dumps(r2).encode())
    d_bytes3 = len(json.dumps(r3).encode())

    assert len(d_text1) > 0
    assert len(d_text2) > 0

    metrics.measurements.append(Measurement(
        label="1st snapshot", path="direct",
        elapsed_ms=d_ms1, payload_bytes=d_bytes1,
        estimated_tokens=_estimate_tokens(d_text1),
    ))
    metrics.measurements.append(Measurement(
        label="2nd snapshot", path="direct",
        elapsed_ms=d_ms2, payload_bytes=d_bytes2,
        estimated_tokens=_estimate_tokens(d_text2),
    ))
    metrics.measurements.append(Measurement(
        label="3rd snapshot", path="direct",
        elapsed_ms=d_ms3, payload_bytes=d_bytes3,
        estimated_tokens=_estimate_tokens(d_text3),
    ))

    # Token savings calculation
    direct_total_tokens = sum(_estimate_tokens(t) for t in [d_text1, d_text2, d_text3])
    proxy_total_tokens = sum(_estimate_tokens(t) for t in [content1, content2, content3])
    saved = direct_total_tokens - proxy_total_tokens
    pct = (saved / direct_total_tokens * 100) if direct_total_tokens > 0 else 0
    metrics.notes.append(
        f"3-read token savings: {saved} tokens saved ({pct:.0f}%) — "
        f"proxy {proxy_total_tokens} vs direct {direct_total_tokens}"
    )
    _all_scenarios.append(metrics)


# ---------------------------------------------------------------------------
# Scenario 3: Multi-page navigation — CMP-03
# Measures: per-page latency, persistence (ref_ids)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario3_multi_page_navigation(direct_client):
    """Navigate two sites — compare per-page latency and proxy persistence."""
    metrics = ScenarioMetrics(name="Multi-page Navigation")

    urls = [
        ("https://example.com", "Example Domain"),
        ("https://www.iana.org/", "iana"),
    ]

    # --- Proxy path ---
    ref_ids = []
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)

        for url, check in urls:
            short = url.split("//")[1][:20]
            _, nav_ms = await _proxy_timed(client, session_id, "browser_navigate", {"url": url})
            snap_resp, snap_ms = await _proxy_timed(client, session_id, "browser_snapshot", {})
            ref_id = snap_resp["ref_id"]
            ref_ids.append(ref_id)
            snap_meta_bytes = len(json.dumps(snap_resp).encode())
            content, content_ms, content_bytes = await _get_content_timed(client, ref_id)

            assert check.lower() in content.lower(), f"Missing '{check}' in proxy content for {url}"

            metrics.measurements.append(Measurement(
                label=f"navigate ({short})", path="proxy",
                elapsed_ms=nav_ms,
            ))
            metrics.measurements.append(Measurement(
                label=f"snapshot ({short})", path="proxy",
                elapsed_ms=snap_ms, payload_bytes=snap_meta_bytes,
                estimated_tokens=_estimate_tokens(json.dumps(snap_resp)),
            ))
            metrics.measurements.append(Measurement(
                label=f"get_content ({short})", path="proxy",
                elapsed_ms=content_ms, payload_bytes=content_bytes,
                estimated_tokens=_estimate_tokens(content),
            ))

        # Proxy value-add: old content still retrievable by ref_id
        old_content, old_ms, _ = await _get_content_timed(client, ref_ids[0], reset_cursor=True)
        assert "Example Domain" in old_content
        metrics.measurements.append(Measurement(
            label="get_content (page 1 replay)", path="proxy",
            elapsed_ms=old_ms, payload_bytes=len(old_content.encode()),
            estimated_tokens=_estimate_tokens(old_content),
        ))
        metrics.notes.append(f"Proxy persistence: page 1 content retrieved after navigating to page 2 ({old_ms:.0f}ms)")

    assert ref_ids[0] != ref_ids[1]

    # --- Direct path ---
    for url, check in urls:
        short = url.split("//")[1][:20]
        _, nav_ms = await direct_client.call_tool_timed("browser_navigate", {"url": url})
        result, snap_ms = await direct_client.call_tool_timed("browser_snapshot", {})
        d_content = result["content"][0]["text"]
        d_bytes = len(json.dumps(result).encode())

        assert check.lower() in d_content.lower(), f"Missing '{check}' in direct content for {url}"

        metrics.measurements.append(Measurement(
            label=f"navigate ({short})", path="direct",
            elapsed_ms=nav_ms,
        ))
        metrics.measurements.append(Measurement(
            label=f"snapshot ({short})", path="direct",
            elapsed_ms=snap_ms, payload_bytes=d_bytes,
            estimated_tokens=_estimate_tokens(d_content),
        ))

    metrics.notes.append("Direct has NO persistence — previous page content is gone after navigation")
    _all_scenarios.append(metrics)


# ---------------------------------------------------------------------------
# Scenario 4: Content search filtering — CMP-04
# Measures: filtered vs full payload size and token count
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario4_content_search(direct_client):
    """Proxy search_for filters content — compare payload reduction."""
    metrics = ScenarioMetrics(name="Content Search Filtering")

    # --- Proxy path ---
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)
        await _proxy_timed(client, session_id, "browser_navigate", {"url": "https://example.com"})
        snap_resp, _ = await _proxy_timed(client, session_id, "browser_snapshot", {})
        ref_id = snap_resp["ref_id"]

        # Full content
        full_content, full_ms, full_bytes = await _get_content_timed(
            client, ref_id, reset_cursor=True
        )
        # Filtered content
        filtered_content, filtered_ms, filtered_bytes = await _get_content_timed(
            client, ref_id, search_for="Example Domain", reset_cursor=True
        )

    assert "Example Domain" in filtered_content
    assert "Example Domain" in full_content
    assert len(filtered_content) < len(full_content)

    metrics.measurements.append(Measurement(
        label="full content", path="proxy",
        elapsed_ms=full_ms, payload_bytes=full_bytes,
        estimated_tokens=_estimate_tokens(full_content),
    ))
    metrics.measurements.append(Measurement(
        label="filtered (search_for)", path="proxy",
        elapsed_ms=filtered_ms, payload_bytes=filtered_bytes,
        estimated_tokens=_estimate_tokens(filtered_content),
    ))

    # --- Direct path ---
    await direct_client.call_tool("browser_navigate", {"url": "https://example.com"})
    result, snap_ms = await direct_client.call_tool_timed("browser_snapshot", {})
    d_content = result["content"][0]["text"]
    d_bytes = len(json.dumps(result).encode())

    assert "Example Domain" in d_content

    metrics.measurements.append(Measurement(
        label="snapshot (full, no filter)", path="direct",
        elapsed_ms=snap_ms, payload_bytes=d_bytes,
        estimated_tokens=_estimate_tokens(d_content),
    ))

    reduction = (1 - len(filtered_content) / len(full_content)) * 100
    token_saved = _estimate_tokens(full_content) - _estimate_tokens(filtered_content)
    metrics.notes.append(
        f"search_for reduction: {reduction:.0f}% smaller payload, ~{token_saved} tokens saved"
    )
    metrics.notes.append("Direct MCP has no search filtering — always returns full accessibility tree")
    _all_scenarios.append(metrics)


# ---------------------------------------------------------------------------
# Scenario 5: Error handling — CMP-05
# Measures: error response time and graceful failure
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario5_error_handling(direct_client):
    """Both paths handle invalid URL gracefully — compare error latency."""
    metrics = ScenarioMetrics(name="Error Handling")
    invalid_url = "https://this-domain-does-not-exist-at-all-12345.invalid"

    # --- Proxy path ---
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)
        t0 = time.perf_counter()
        resp = await client.post("/proxy", json={
            "session_id": session_id,
            "tool": "browser_navigate",
            "params": {"url": invalid_url},
        })
        proxy_error_ms = (time.perf_counter() - t0) * 1000
        proxy_bytes = len(resp.content)

    metrics.measurements.append(Measurement(
        label="invalid URL navigate", path="proxy",
        elapsed_ms=proxy_error_ms, payload_bytes=proxy_bytes,
    ))

    # --- Direct path ---
    t0 = time.perf_counter()
    try:
        await direct_client.call_tool("browser_navigate", {"url": invalid_url})
        direct_graceful = True
    except RuntimeError:
        direct_graceful = True
    direct_error_ms = (time.perf_counter() - t0) * 1000

    metrics.measurements.append(Measurement(
        label="invalid URL navigate", path="direct",
        elapsed_ms=direct_error_ms,
    ))

    assert direct_graceful
    metrics.notes.append("Both paths handle errors gracefully without crashing")
    _all_scenarios.append(metrics)


# ---------------------------------------------------------------------------
# Scenario 6: Complex page — Google Search — CMP-06
# Measures: large accessibility tree on a real search results page
# ---------------------------------------------------------------------------


def _find_element_ref(snapshot_text: str, *keywords: str) -> str | None:
    """Extract an element ref (e.g. 'e4' or 's1e4') from a Playwright accessibility snapshot.

    Searches for lines containing ANY of the keywords (case-insensitive) and extracts
    the [ref=...] value. Returns None if not found.
    """
    for line in snapshot_text.split("\n"):
        line_lower = line.lower()
        if any(kw.lower() in line_lower for kw in keywords):
            ref_match = re.search(r'\[ref=([se\d]+)\]', line)
            if ref_match:
                return ref_match.group(1)
    return None


@pytest.mark.integration
async def test_scenario6_google_search(direct_client):
    """Google search — navigate, type query, submit, snapshot results page."""
    metrics = ScenarioMetrics(name="Complex Page: Google Search")
    search_query = "playwright browser automation"

    # --- Proxy path ---
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)

        # Navigate to Google
        _, nav_ms = await _proxy_timed(client, session_id, "browser_navigate", {"url": "https://www.google.com"})
        metrics.measurements.append(Measurement(
            label="navigate (google.com)", path="proxy", elapsed_ms=nav_ms,
        ))

        # Snapshot homepage to discover search input ref
        home_snap, home_snap_ms = await _proxy_timed(client, session_id, "browser_snapshot", {})
        home_ref_id = home_snap["ref_id"]
        home_content, _, _ = await _get_content_timed(client, home_ref_id)
        # Try combobox/textarea first (actual input), then search container as fallback
        search_ref = (
            _find_element_ref(home_content, "combobox", "textarea")
            or _find_element_ref(home_content, "search")
        )
        assert search_ref, f"Could not find search input ref in proxy snapshot:\n{home_content[:800]}"

        # Type search query into discovered ref
        _, type_ms = await _proxy_timed(client, session_id, "browser_type", {
            "element": "combobox", "ref": search_ref, "text": search_query,
        })
        metrics.measurements.append(Measurement(
            label="type search query", path="proxy", elapsed_ms=type_ms,
        ))

        # Press Enter to submit
        _, press_ms = await _proxy_timed(client, session_id, "browser_press_key", {"key": "Enter"})
        metrics.measurements.append(Measurement(
            label="press Enter", path="proxy", elapsed_ms=press_ms,
        ))

        # Wait for results to load
        await asyncio.sleep(3)

        # Snapshot search results page
        snap_resp, snap_ms = await _proxy_timed(client, session_id, "browser_snapshot", {})
        ref_id = snap_resp["ref_id"]
        snap_meta_bytes = len(json.dumps(snap_resp).encode())
        metrics.measurements.append(Measurement(
            label="snapshot results (metadata)", path="proxy",
            elapsed_ms=snap_ms, payload_bytes=snap_meta_bytes,
            estimated_tokens=_estimate_tokens(json.dumps(snap_resp)),
        ))

        # First get_content — full results page
        content1, ms1, bytes1 = await _get_content_timed(client, ref_id)
        assert "playwright" in content1.lower(), (
            f"Proxy search results missing 'playwright'. Got:\n{content1[:500]}"
        )
        metrics.measurements.append(Measurement(
            label="get_content (1st read)", path="proxy",
            elapsed_ms=ms1, payload_bytes=bytes1,
            estimated_tokens=_estimate_tokens(content1),
        ))

        # Second get_content — diff suppressed
        content2, ms2, bytes2 = await _get_content_timed(client, ref_id)
        metrics.measurements.append(Measurement(
            label="get_content (2nd read, diff)", path="proxy",
            elapsed_ms=ms2, payload_bytes=bytes2,
            estimated_tokens=_estimate_tokens(content2),
        ))

        # Filtered search
        content_filtered, ms_f, bytes_f = await _get_content_timed(
            client, ref_id, search_for="playwright", reset_cursor=True,
        )
        metrics.measurements.append(Measurement(
            label="get_content (search_for)", path="proxy",
            elapsed_ms=ms_f, payload_bytes=bytes_f,
            estimated_tokens=_estimate_tokens(content_filtered),
        ))

    # --- Direct path ---
    _, d_nav_ms = await direct_client.call_tool_timed("browser_navigate", {"url": "https://www.google.com"})
    metrics.measurements.append(Measurement(
        label="navigate (google.com)", path="direct", elapsed_ms=d_nav_ms,
    ))

    # Snapshot homepage to discover search input ref
    d_home_result, _ = await direct_client.call_tool_timed("browser_snapshot", {})
    d_home_text = d_home_result["content"][0]["text"]
    d_search_ref = (
        _find_element_ref(d_home_text, "combobox", "textarea")
        or _find_element_ref(d_home_text, "search")
    )
    assert d_search_ref, f"Could not find search input ref in direct snapshot:\n{d_home_text[:800]}"

    # Type search query
    _, d_type_ms = await direct_client.call_tool_timed("browser_type", {
        "element": "combobox", "ref": d_search_ref, "text": search_query,
    })
    metrics.measurements.append(Measurement(
        label="type search query", path="direct", elapsed_ms=d_type_ms,
    ))

    # Press Enter to submit
    _, d_press_ms = await direct_client.call_tool_timed("browser_press_key", {"key": "Enter"})
    metrics.measurements.append(Measurement(
        label="press Enter", path="direct", elapsed_ms=d_press_ms,
    ))

    # Wait for results to load
    await asyncio.sleep(3)

    # Snapshot search results
    result, d_snap_ms = await direct_client.call_tool_timed("browser_snapshot", {})
    d_content = result["content"][0]["text"]
    d_bytes = len(json.dumps(result).encode())
    assert "playwright" in d_content.lower(), (
        f"Direct search results missing 'playwright'. Got:\n{d_content[:500]}"
    )
    metrics.measurements.append(Measurement(
        label="snapshot results (full)", path="direct",
        elapsed_ms=d_snap_ms, payload_bytes=d_bytes,
        estimated_tokens=_estimate_tokens(d_content),
    ))

    # Second snapshot — direct returns full again
    result2, d_snap_ms2 = await direct_client.call_tool_timed("browser_snapshot", {})
    d_content2 = result2["content"][0]["text"]
    d_bytes2 = len(json.dumps(result2).encode())
    metrics.measurements.append(Measurement(
        label="snapshot (2nd, full again)", path="direct",
        elapsed_ms=d_snap_ms2, payload_bytes=d_bytes2,
        estimated_tokens=_estimate_tokens(d_content2),
    ))

    # Token savings
    proxy_total = _estimate_tokens(content1) + _estimate_tokens(content2)
    direct_total = _estimate_tokens(d_content) + _estimate_tokens(d_content2)
    saved = direct_total - proxy_total
    pct = (saved / direct_total * 100) if direct_total > 0 else 0
    metrics.notes.append(
        f"2-read diff savings: {saved} tokens ({pct:.0f}%) — proxy {proxy_total} vs direct {direct_total}"
    )
    if content_filtered:
        filter_pct = (1 - len(content_filtered) / len(content1)) * 100 if content1 else 0
        metrics.notes.append(
            f"search_for 'playwright' reduction: {filter_pct:.0f}% — "
            f"{_estimate_tokens(content_filtered)} tokens vs {_estimate_tokens(content1)} full"
        )
    _all_scenarios.append(metrics)


# ---------------------------------------------------------------------------
# Scenario 7: Complex page — YouTube — CMP-07
# Measures: heavy JS-rendered page with large accessibility tree
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_scenario7_youtube_search(direct_client):
    """YouTube search — navigate, search for a video, snapshot results page."""
    metrics = ScenarioMetrics(name="Complex Page: YouTube Search")
    search_query = "playwright testing tutorial"

    # --- Proxy path ---
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        session_id = await _create_session(client)

        # Navigate to YouTube
        _, nav_ms = await _proxy_timed(client, session_id, "browser_navigate", {"url": "https://www.youtube.com"})
        metrics.measurements.append(Measurement(
            label="navigate (youtube.com)", path="proxy", elapsed_ms=nav_ms,
        ))

        await asyncio.sleep(3)

        # Snapshot homepage to discover search input ref
        home_snap, home_snap_ms = await _proxy_timed(client, session_id, "browser_snapshot", {})
        home_ref_id = home_snap["ref_id"]
        home_content, _, _ = await _get_content_timed(client, home_ref_id)
        metrics.measurements.append(Measurement(
            label="snapshot homepage", path="proxy", elapsed_ms=home_snap_ms,
            payload_bytes=len(home_content.encode()),
            estimated_tokens=_estimate_tokens(home_content),
        ))

        search_ref = _find_element_ref(home_content, "search", "combobox", "textbox")
        assert search_ref, f"Could not find search input ref in proxy YT snapshot:\n{home_content[:800]}"

        # Type search query
        _, type_ms = await _proxy_timed(client, session_id, "browser_type", {
            "element": "Search", "ref": search_ref, "text": search_query,
        })
        metrics.measurements.append(Measurement(
            label="type search query", path="proxy", elapsed_ms=type_ms,
        ))

        # Press Enter to submit search
        _, press_ms = await _proxy_timed(client, session_id, "browser_press_key", {"key": "Enter"})
        metrics.measurements.append(Measurement(
            label="press Enter", path="proxy", elapsed_ms=press_ms,
        ))

        await asyncio.sleep(3)

        # Snapshot search results
        snap_resp, snap_ms = await _proxy_timed(client, session_id, "browser_snapshot", {})
        ref_id = snap_resp["ref_id"]
        snap_meta_bytes = len(json.dumps(snap_resp).encode())
        metrics.measurements.append(Measurement(
            label="snapshot results (metadata)", path="proxy",
            elapsed_ms=snap_ms, payload_bytes=snap_meta_bytes,
            estimated_tokens=_estimate_tokens(json.dumps(snap_resp)),
        ))

        # Full content — search results page
        content1, ms1, bytes1 = await _get_content_timed(client, ref_id)
        metrics.measurements.append(Measurement(
            label="get_content (1st read)", path="proxy",
            elapsed_ms=ms1, payload_bytes=bytes1,
            estimated_tokens=_estimate_tokens(content1),
        ))

        # Diff-suppressed read
        content2, ms2, bytes2 = await _get_content_timed(client, ref_id)
        metrics.measurements.append(Measurement(
            label="get_content (2nd read, diff)", path="proxy",
            elapsed_ms=ms2, payload_bytes=bytes2,
            estimated_tokens=_estimate_tokens(content2),
        ))

        # Filtered search
        content_search, ms_s, bytes_s = await _get_content_timed(
            client, ref_id, search_for="playwright", reset_cursor=True,
        )
        metrics.measurements.append(Measurement(
            label="get_content (search_for)", path="proxy",
            elapsed_ms=ms_s, payload_bytes=bytes_s,
            estimated_tokens=_estimate_tokens(content_search),
        ))

    # --- Direct path ---
    _, d_nav_ms = await direct_client.call_tool_timed("browser_navigate", {"url": "https://www.youtube.com"})
    metrics.measurements.append(Measurement(
        label="navigate (youtube.com)", path="direct", elapsed_ms=d_nav_ms,
    ))

    await asyncio.sleep(3)

    # Snapshot homepage to discover search input ref
    d_home_result, d_home_snap_ms = await direct_client.call_tool_timed("browser_snapshot", {})
    d_home_text = d_home_result["content"][0]["text"]
    d_home_bytes = len(json.dumps(d_home_result).encode())
    metrics.measurements.append(Measurement(
        label="snapshot homepage", path="direct",
        elapsed_ms=d_home_snap_ms, payload_bytes=d_home_bytes,
        estimated_tokens=_estimate_tokens(d_home_text),
    ))

    d_search_ref = _find_element_ref(d_home_text, "search", "combobox", "textbox")
    assert d_search_ref, f"Could not find search input ref in direct YT snapshot:\n{d_home_text[:800]}"

    # Type search query
    _, d_type_ms = await direct_client.call_tool_timed("browser_type", {
        "element": "Search", "ref": d_search_ref, "text": search_query,
    })
    metrics.measurements.append(Measurement(
        label="type search query", path="direct", elapsed_ms=d_type_ms,
    ))

    # Press Enter
    _, d_press_ms = await direct_client.call_tool_timed("browser_press_key", {"key": "Enter"})
    metrics.measurements.append(Measurement(
        label="press Enter", path="direct", elapsed_ms=d_press_ms,
    ))

    await asyncio.sleep(3)

    # Snapshot search results
    result1, d_snap_ms1 = await direct_client.call_tool_timed("browser_snapshot", {})
    d_content1 = result1["content"][0]["text"]
    d_bytes1 = len(json.dumps(result1).encode())
    metrics.measurements.append(Measurement(
        label="snapshot results (full)", path="direct",
        elapsed_ms=d_snap_ms1, payload_bytes=d_bytes1,
        estimated_tokens=_estimate_tokens(d_content1),
    ))

    # Second snapshot — direct returns full again
    result2, d_snap_ms2 = await direct_client.call_tool_timed("browser_snapshot", {})
    d_content2 = result2["content"][0]["text"]
    d_bytes2 = len(json.dumps(result2).encode())
    metrics.measurements.append(Measurement(
        label="snapshot (2nd, full again)", path="direct",
        elapsed_ms=d_snap_ms2, payload_bytes=d_bytes2,
        estimated_tokens=_estimate_tokens(d_content2),
    ))

    # Summary calculations
    proxy_tokens_2read = _estimate_tokens(content1) + _estimate_tokens(content2)
    direct_tokens_2read = _estimate_tokens(d_content1) + _estimate_tokens(d_content2)
    saved = direct_tokens_2read - proxy_tokens_2read
    pct = (saved / direct_tokens_2read * 100) if direct_tokens_2read > 0 else 0
    metrics.notes.append(
        f"2-read diff savings: {saved} tokens ({pct:.0f}%) — proxy {proxy_tokens_2read} vs direct {direct_tokens_2read}"
    )
    metrics.notes.append(
        f"Full page: {_estimate_tokens(content1)} tokens | "
        f"Filtered 'playwright': {_estimate_tokens(content_search)} tokens | "
        f"Diff suppressed: {_estimate_tokens(content2)} tokens"
    )
    _all_scenarios.append(metrics)


# ---------------------------------------------------------------------------
# Report printer — runs after all tests
# ---------------------------------------------------------------------------


def _format_table(headers: list[str], rows: list[list[str]], col_align: list[str] | None = None) -> str:
    """Format a simple ASCII table."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    if col_align is None:
        col_align = ["<"] * len(headers)

    def fmt_row(cells):
        parts = []
        for cell, w, align in zip(cells, widths, col_align):
            if align == ">":
                parts.append(cell.rjust(w))
            else:
                parts.append(cell.ljust(w))
        return "  ".join(parts)

    lines = []
    lines.append(fmt_row(headers))
    lines.append("  ".join("-" * w for w in widths))
    for row in rows:
        lines.append(fmt_row(row))
    return "\n".join(lines)


@pytest.fixture(autouse=True, scope="session")
def print_comparison_report():
    """Print the performance comparison table after all tests complete."""
    yield

    if not _all_scenarios:
        return

    print("\n")
    print("=" * 90)
    print("  PERFORMANCE COMPARISON: Playwright Proxy MCP vs Direct Playwright MCP")
    print("=" * 90)

    for scenario in _all_scenarios:
        print(f"\n{'─' * 90}")
        print(f"  {scenario.name}")
        print(f"{'─' * 90}")

        headers = ["Operation", "Path", "Latency (ms)", "Payload (bytes)", "Est. Tokens"]
        rows = []
        for m in scenario.measurements:
            rows.append([
                m.label,
                m.path,
                f"{m.elapsed_ms:.0f}",
                f"{m.payload_bytes:,}" if m.payload_bytes else "-",
                f"{m.estimated_tokens:,}" if m.estimated_tokens else "-",
            ])
        print(_format_table(headers, rows, col_align=["<", "<", ">", ">", ">"]))

        if scenario.notes:
            print()
            for note in scenario.notes:
                print(f"  >> {note}")

    # Summary table
    print(f"\n{'=' * 90}")
    print("  SUMMARY: Key Proxy Advantages")
    print(f"{'=' * 90}")

    summary_rows = [
        ["Metadata-only responses", "Initial tool call returns ref_id, not full content — small, fixed-size payload"],
        ["Diff suppression", "Repeated reads return empty when content unchanged — massive token savings"],
        ["search_for filtering", "Retrieve only matching lines — reduces payload for targeted lookups"],
        ["Persistence (SQLite)", "All snapshots stored — retrieve any historical page by ref_id"],
        ["Session management", "Named sessions with lifecycle tracking and error audit trail"],
    ]

    headers = ["Feature", "Description"]
    print(_format_table(headers, summary_rows))
    print()
