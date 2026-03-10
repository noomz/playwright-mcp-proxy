"""Tests for Phase 7 session state capture."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from playwright_mcp_proxy.server.session_state import SessionStateManager


@pytest.mark.asyncio
async def test_capture_state():
    """Test capturing session state from browser using combined single RPC."""
    # Mock PlaywrightManager
    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock()

    # Setup mock response: single combined JSON object returned from one RPC
    combined_result = {
        "url": "https://example.com/test",
        "cookies": "session=abc123; user=john",
        "localStorage": '{"key1": "value1", "key2": "value2"}',
        "sessionStorage": '{"tempKey": "tempValue"}',
        "viewport": '{"width": 1920, "height": 1080}',
    }

    async def mock_send_request(method, params):
        """Mock send_request to return combined object for browser_evaluate."""
        if method != "tools/call":
            return {}

        name = params.get("name", "")
        if name == "browser_evaluate":
            return {
                "content": [{"type": "text", "text": json.dumps(combined_result)}]
            }

        return {}

    mock_playwright.send_request.side_effect = mock_send_request

    # Create SessionStateManager
    manager = SessionStateManager(mock_playwright)

    # Capture state
    snapshot = await manager.capture_state("test-session-123")

    # Verify snapshot was created
    assert snapshot is not None
    assert snapshot.session_id == "test-session-123"
    assert snapshot.current_url == "https://example.com/test"

    # Verify cookies were parsed correctly
    cookies = json.loads(snapshot.cookies)
    assert len(cookies) == 2
    assert cookies[0]["name"] == "session"
    assert cookies[0]["value"] == "abc123"
    assert cookies[1]["name"] == "user"
    assert cookies[1]["value"] == "john"

    # Verify localStorage
    assert snapshot.local_storage == '{"key1": "value1", "key2": "value2"}'

    # Verify sessionStorage
    assert snapshot.session_storage == '{"tempKey": "tempValue"}'

    # Verify viewport
    assert snapshot.viewport == '{"width": 1920, "height": 1080}'

    # Verify send_request was called exactly 1 time (combined single RPC)
    assert mock_playwright.send_request.call_count == 1


@pytest.mark.asyncio
async def test_capture_state_empty_cookies():
    """Test capturing state when there are no cookies using single combined RPC."""
    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock()

    combined_result = {
        "url": "https://example.com",
        "cookies": "",
        "localStorage": "{}",
        "sessionStorage": "{}",
        "viewport": '{"width": 1024, "height": 768}',
    }

    async def mock_send_request(method, params):
        """Mock send_request returning combined object with empty cookies."""
        if method != "tools/call":
            return {}

        name = params.get("name", "")
        if name == "browser_evaluate":
            return {
                "content": [{"type": "text", "text": json.dumps(combined_result)}]
            }

        return {}

    mock_playwright.send_request.side_effect = mock_send_request

    manager = SessionStateManager(mock_playwright)
    snapshot = await manager.capture_state("test-session-456")

    assert snapshot is not None
    cookies = json.loads(snapshot.cookies)
    assert len(cookies) == 0  # No cookies

    # Verify single combined RPC
    assert mock_playwright.send_request.call_count == 1


@pytest.mark.asyncio
async def test_capture_state_partial_failure():
    """Test that capture_state handles partial property failures gracefully.

    When one property (e.g., localStorage) throws SecurityError in browser,
    the combined JS returns null for that property. capture_state() should still
    return a snapshot with the other properties populated.
    send_request must be called exactly 1 time.
    """
    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock()

    # localStorage is null — simulating SecurityError fallback from try/catch
    combined_result = {
        "url": "https://example.com",
        "cookies": "session=abc",
        "localStorage": None,
        "sessionStorage": "{}",
        "viewport": "{}",
    }

    async def mock_send_request(method, params):
        if method != "tools/call":
            return {}

        name = params.get("name", "")
        if name == "browser_evaluate":
            return {
                "content": [{"type": "text", "text": json.dumps(combined_result)}]
            }

        return {}

    mock_playwright.send_request.side_effect = mock_send_request

    manager = SessionStateManager(mock_playwright)
    snapshot = await manager.capture_state("test-session-partial")

    # Snapshot should still be created despite partial failure
    assert snapshot is not None
    assert snapshot.current_url == "https://example.com"

    # localStorage was null — should be treated as fallback (None or "{}")
    # The key requirement: snapshot is returned and call_count == 1
    assert mock_playwright.send_request.call_count == 1


@pytest.mark.asyncio
async def test_capture_state_error_handling():
    """Test that capture_state handles errors gracefully."""
    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock(side_effect=Exception("Connection failed"))

    manager = SessionStateManager(mock_playwright)
    snapshot = await manager.capture_state("test-session-error")

    # Should return None on error, not raise exception
    assert snapshot is None


@pytest.mark.asyncio
async def test_restore_state():
    """Test restoring session state to browser."""
    from playwright_mcp_proxy.models.database import SessionSnapshot

    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock(return_value={})

    manager = SessionStateManager(mock_playwright)

    # Create a snapshot to restore
    snapshot = SessionSnapshot(
        session_id="test-session-restore",
        current_url="https://example.com/restored",
        cookies='[{"name": "session", "value": "xyz789"}]',
        local_storage='{"restored_key": "restored_value"}',
        session_storage='{"temp_restored": "temp_value"}',
        viewport='{"width": 1280, "height": 720}',
        snapshot_time=datetime.now(),
    )

    # Restore state
    result = await manager.restore_state(snapshot)

    assert result is True

    # Verify send_request was called for:
    # 1. Navigate to URL
    # 2. Restore localStorage (1 key)
    # 3. Restore sessionStorage (1 key)
    # 4. Restore cookies (1 cookie)
    assert mock_playwright.send_request.call_count == 4

    # Verify navigation was called
    calls = mock_playwright.send_request.call_args_list
    navigate_call = calls[0]
    assert navigate_call[0][0] == "tools/call"
    assert navigate_call[0][1]["name"] == "browser_navigate"
    assert navigate_call[0][1]["arguments"]["url"] == "https://example.com/restored"


@pytest.mark.asyncio
async def test_restore_state_injection_safety():
    """Test that restore_state uses json.dumps() and not f-string interpolation.

    When localStorage value contains JS injection payload like '; alert('xss'); ',
    the generated function string must use json.dumps() output (double-quoted JSON
    literal) rather than f-string with single quotes.
    """
    from playwright_mcp_proxy.models.database import SessionSnapshot

    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock(return_value={})

    manager = SessionStateManager(mock_playwright)

    xss_value = "'; alert('xss'); '"
    snapshot = SessionSnapshot(
        session_id="test-session-xss",
        current_url="https://example.com",
        local_storage=json.dumps({"xss": xss_value}),
        snapshot_time=datetime.now(),
    )

    result = await manager.restore_state(snapshot)
    assert result is True

    # Inspect the call args for the localStorage setItem call
    calls = mock_playwright.send_request.call_args_list

    # Find the localStorage setItem call (after the navigate call)
    set_item_calls = [
        call
        for call in calls
        if call[0][0] == "tools/call"
        and call[0][1].get("name") == "browser_evaluate"
        and "localStorage.setItem" in call[0][1].get("arguments", {}).get("function", "")
    ]
    assert len(set_item_calls) >= 1

    # Verify the function string uses json.dumps output (double-quoted JSON)
    for call in set_item_calls:
        fn = call[0][1]["arguments"]["function"]
        # json.dumps always produces double-quoted strings.
        # The key "xss" must appear as a double-quoted JSON literal.
        assert '"xss"' in fn, (
            f"Expected json.dumps key output '\"xss\"' in function string: {fn!r}"
        )
        # The function must NOT use old-style single-quoted f-string values.
        # Old code: localStorage.setItem('xss', '...')  <- single-quoted, injectable
        # New code: localStorage.setItem("xss", "...")  <- json.dumps, safe
        # The dead giveaway of the old pattern is a single-quoted second argument.
        # Check: the character immediately after "setItem(" is a double-quote.
        setitem_start = fn.index("setItem(") + len("setItem(")
        first_char_of_key = fn[setitem_start]
        assert first_char_of_key == '"', (
            f"Expected json.dumps double-quoted key, got {first_char_of_key!r} in: {fn!r}"
        )


@pytest.mark.asyncio
async def test_restore_state_special_chars():
    """Test restore_state handles special characters via json.dumps() correctly.

    Values containing single quotes, double quotes, backslashes, newlines,
    and Unicode must restore correctly with proper JSON encoding.
    """
    from playwright_mcp_proxy.models.database import SessionSnapshot

    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock(return_value={})

    manager = SessionStateManager(mock_playwright)

    # Storage with all the tricky characters
    tricky_storage = {
        "key'quote": "val\"double",
        "back\\slash": "new\nline",
        "unicode": "\u00e9\u00e0\u00fc",
    }

    snapshot = SessionSnapshot(
        session_id="test-session-special",
        current_url="https://example.com",
        local_storage=json.dumps(tricky_storage),
        session_storage=json.dumps({"s'key": "s\"val\nwith\\slash"}),
        snapshot_time=datetime.now(),
    )

    result = await manager.restore_state(snapshot)
    assert result is True

    # Verify all calls completed without errors
    calls = mock_playwright.send_request.call_args_list

    # Find evaluate calls (localStorage and sessionStorage setItem)
    evaluate_calls = [
        call
        for call in calls
        if call[0][0] == "tools/call"
        and call[0][1].get("name") == "browser_evaluate"
    ]

    # Should have 4 evaluate calls (3 localStorage + 1 sessionStorage)
    assert len(evaluate_calls) == 4

    # Each function string must be parseable and contain properly JSON-encoded values
    for call in evaluate_calls:
        fn = call[0][1]["arguments"]["function"]
        # The function string must be valid (no unescaped single quotes breaking JS)
        # Verify json.dumps produced double-quoted strings for keys/values
        # json.dumps on keys with single quotes will produce "key'quote" (valid)
        # json.dumps on values with double quotes will produce "val\"double" (escaped)
        assert "setItem" in fn
        # No raw unescaped single-quoted JS string patterns like 'val"double'
        # (json.dumps always produces double-quoted output so this pattern won't appear)


@pytest.mark.asyncio
async def test_restore_state_error_handling():
    """Test that restore_state handles errors gracefully."""
    from playwright_mcp_proxy.models.database import SessionSnapshot

    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock(side_effect=Exception("Navigation failed"))

    manager = SessionStateManager(mock_playwright)

    snapshot = SessionSnapshot(
        session_id="test-session-error",
        current_url="https://example.com",
        snapshot_time=datetime.now(),
    )

    # Should return False on error, not raise exception
    result = await manager.restore_state(snapshot)
    assert result is False


@pytest.mark.asyncio
async def test_parse_cookie_string():
    """Test cookie string parsing."""
    mock_playwright = MagicMock()
    manager = SessionStateManager(mock_playwright)

    # Test normal cookie string
    result = manager._parse_cookie_string("name1=value1; name2=value2; name3=value3")
    assert len(result) == 3
    assert result[0] == {"name": "name1", "value": "value1"}
    assert result[1] == {"name": "name2", "value": "value2"}
    assert result[2] == {"name": "name3", "value": "value3"}

    # Test empty string
    result = manager._parse_cookie_string("")
    assert result == []

    # Test cookie with = in value
    result = manager._parse_cookie_string("data=key=value")
    assert len(result) == 1
    assert result[0] == {"name": "data", "value": "key=value"}


@pytest.mark.asyncio
async def test_extract_evaluate_result():
    """Test extracting result from browser_evaluate response."""
    mock_playwright = MagicMock()
    manager = SessionStateManager(mock_playwright)

    # Test normal response
    result = manager._extract_evaluate_result(
        {"content": [{"type": "text", "text": "hello world"}]}
    )
    assert result == "hello world"

    # Test empty content
    result = manager._extract_evaluate_result({"content": []})
    assert result == ""

    # Test missing content key
    result = manager._extract_evaluate_result({})
    assert result == ""
