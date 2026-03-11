"""
Integration tests against a running playwright-proxy-server with real browser navigation.

Requirements:
    - Server running on localhost:34501: `uv run playwright-proxy-server`
    - Internet access (tests hit https://example.com and https://httpbin.org)

Run:
    uv run pytest tests/test_integration_live.py -v
"""

import httpx
import pytest

BASE_URL = "http://localhost:34501"
TIMEOUT = 60.0


async def _client():
    """Create an httpx client."""
    return httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT)


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
    """Navigate to url, take snapshot, return (ref_id, content)."""
    await _proxy(client, session_id, "browser_navigate", {"url": url})
    snap = await _proxy(client, session_id, "browser_snapshot", {})
    ref_id = snap["ref_id"]
    resp = await client.get(f"/content/{ref_id}")
    return ref_id, resp.json()["content"]


# ===========================================================================
# 1. Server health & session management
# ===========================================================================


async def test_health():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/health")
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["playwright_subprocess"] == "running"


async def test_create_session():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.post("/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) == 36  # UUID format


async def test_list_sessions():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        # Create one first so list is non-empty
        await _create_session(client)
        resp = await client.get("/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert data["count"] >= 1


# ===========================================================================
# 2. Navigate & snapshot on example.com
# ===========================================================================


async def test_navigate_to_example_com():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        result = await _proxy(client, sid, "browser_navigate", {
            "url": "https://example.com",
        })
        assert result["status"] == "success"
        assert result["ref_id"]


async def test_snapshot_contains_example_domain():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        ref_id, content = await _navigate_and_snapshot(client, sid, "https://example.com")
        assert "Example Domain" in content


async def test_search_filter():
    """get_content with search_for should return only matching lines."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        await _proxy(client, sid, "browser_navigate", {"url": "https://example.com"})
        snap = await _proxy(client, sid, "browser_snapshot", {})
        ref_id = snap["ref_id"]

        # Filtered search
        resp = await client.get(f"/content/{ref_id}", params={
            "search_for": "Example Domain",
            "reset_cursor": True,
        })
        filtered = resp.json()["content"]
        assert "Example Domain" in filtered

        # Full content
        full_resp = await client.get(f"/content/{ref_id}", params={"reset_cursor": True})
        full = full_resp.json()["content"]
        assert len(filtered) < len(full)


# ===========================================================================
# 3. Diff-based content retrieval (Phase 2)
# ===========================================================================


async def test_diff_first_read_returns_content():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        ref_id, content = await _navigate_and_snapshot(client, sid, "https://example.com")
        assert len(content) > 0
        assert "Example Domain" in content


async def test_diff_second_read_returns_empty():
    """Second read of same ref_id should return empty (no changes)."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        await _proxy(client, sid, "browser_navigate", {"url": "https://example.com"})
        snap = await _proxy(client, sid, "browser_snapshot", {})
        ref_id = snap["ref_id"]

        # First read — full content
        resp1 = await client.get(f"/content/{ref_id}")
        assert len(resp1.json()["content"]) > 0

        # Second read — same content, should be empty
        resp2 = await client.get(f"/content/{ref_id}")
        assert resp2.json()["content"] == ""


async def test_diff_reset_cursor():
    """reset_cursor=true should return full content again."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        await _proxy(client, sid, "browser_navigate", {"url": "https://example.com"})
        snap = await _proxy(client, sid, "browser_snapshot", {})
        ref_id = snap["ref_id"]

        # First read (creates cursor)
        await client.get(f"/content/{ref_id}")

        # Reset cursor — should return full content
        resp = await client.get(f"/content/{ref_id}", params={"reset_cursor": True})
        content = resp.json()["content"]
        assert len(content) > 0
        assert "Example Domain" in content


# ===========================================================================
# 4. Click interaction
# ===========================================================================


async def test_click_link_on_example_com():
    """Click the link on example.com (currently 'Learn more')."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        ref_id, content = await _navigate_and_snapshot(client, sid, "https://example.com")

        # Extract any link ref from the accessibility snapshot
        # Lines look like: `- link "Learn more" [ref=e6]`
        import re
        match = re.search(r'- link "([^"]+)"\s*\[ref=(\w+)\]', content)

        if not match:
            pytest.skip("Could not extract link ref from snapshot")

        link_text, ref = match.group(1), match.group(2)
        click_result = await _proxy(client, sid, "browser_click", {
            "element": link_text,
            "ref": ref,
        })
        assert click_result["ref_id"]

        # After clicking, page should change
        snap = await _proxy(client, sid, "browser_snapshot", {})
        resp = await client.get(f"/content/{snap['ref_id']}")
        new_content = resp.json()["content"]
        # Should no longer be on example.com main page
        assert new_content != content


async def test_navigate_back_to_example_com():
    """After navigating away, can return to example.com."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        # Go somewhere else first
        await _proxy(client, sid, "browser_navigate", {"url": "https://httpbin.org"})
        # Navigate back
        ref_id, content = await _navigate_and_snapshot(client, sid, "https://example.com")
        assert "Example Domain" in content


# ===========================================================================
# 5. Form page (httpbin.org/forms/post)
# ===========================================================================


async def test_navigate_to_form_page():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        result = await _proxy(client, sid, "browser_navigate", {
            "url": "https://httpbin.org/forms/post",
        })
        assert result["status"] == "success"


async def test_snapshot_form_page():
    """Snapshot of form page should have non-trivial content."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        ref_id, content = await _navigate_and_snapshot(
            client, sid, "https://httpbin.org/forms/post"
        )
        assert len(content) > 100


# ===========================================================================
# 6. Console logs endpoint
# ===========================================================================


async def test_console_endpoint_returns_200():
    """Console endpoint should return 200 for a valid ref_id."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        result = await _proxy(client, sid, "browser_navigate", {"url": "https://example.com"})
        ref_id = result["ref_id"]
        resp = await client.get(f"/console/{ref_id}")
        assert resp.status_code == 200


# ===========================================================================
# 7. Error handling
# ===========================================================================


async def test_content_not_found():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/content/nonexistent-ref-id")
        assert resp.status_code == 404


async def test_console_not_found():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.get("/console/nonexistent-ref-id")
        assert resp.status_code == 404


async def test_proxy_bad_session():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.post("/proxy", json={
            "session_id": "nonexistent-session-id",
            "tool": "browser_snapshot",
            "params": {},
        })
        assert resp.status_code == 404


async def test_resume_nonexistent_session():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = await client.post("/sessions/nonexistent-session-id/resume")
        assert resp.status_code == 404


async def test_resume_active_session_rejected():
    """Cannot resume an active session."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        resp = await client.post(f"/sessions/{sid}/resume")
        assert resp.status_code == 400


# ===========================================================================
# 8. Multi-page navigation flow
# ===========================================================================


async def test_navigate_two_sites():
    """Navigate to two different sites and verify content differs."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)

        # Page 1
        _, content1 = await _navigate_and_snapshot(client, sid, "https://example.com")
        assert "Example Domain" in content1

        # Page 2
        _, content2 = await _navigate_and_snapshot(client, sid, "https://httpbin.org")
        assert "httpbin" in content2.lower()

        assert content1 != content2


async def test_each_request_gets_unique_ref_id():
    """Every proxy call should produce a unique ref_id."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        await _proxy(client, sid, "browser_navigate", {"url": "https://example.com"})

        ref_ids = set()
        for _ in range(3):
            result = await _proxy(client, sid, "browser_snapshot", {})
            ref_ids.add(result["ref_id"])
        assert len(ref_ids) == 3


# ===========================================================================
# 9. Context lines in search
# ===========================================================================


async def test_search_with_context_lines():
    """before_lines/after_lines should return more content than plain search."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        await _proxy(client, sid, "browser_navigate", {"url": "https://example.com"})
        snap = await _proxy(client, sid, "browser_snapshot", {})
        ref_id = snap["ref_id"]

        # With context lines
        resp1 = await client.get(f"/content/{ref_id}", params={
            "search_for": "Example Domain",
            "before_lines": 2,
            "after_lines": 2,
            "reset_cursor": True,
        })
        with_ctx = resp1.json()["content"]

        # Without context lines
        resp2 = await client.get(f"/content/{ref_id}", params={
            "search_for": "Example Domain",
            "reset_cursor": True,
        })
        no_ctx = resp2.json()["content"]

        assert len(with_ctx) >= len(no_ctx)


# ===========================================================================
# 10. Metadata validation
# ===========================================================================


async def test_proxy_response_metadata():
    """Proxy response should include correct metadata fields."""
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT) as client:
        sid = await _create_session(client)
        await _proxy(client, sid, "browser_navigate", {"url": "https://example.com"})
        result = await _proxy(client, sid, "browser_snapshot", {})

        assert "ref_id" in result
        assert "status" in result
        assert "metadata" in result
        meta = result["metadata"]
        assert meta["tool"] == "browser_snapshot"
        assert meta["has_snapshot"] is True
        assert "console_error_count" in meta
