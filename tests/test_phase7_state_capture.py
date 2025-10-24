"""Tests for Phase 7 session state capture."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from playwright_mcp_proxy.server.session_state import SessionStateManager


@pytest.mark.asyncio
async def test_capture_state():
    """Test capturing session state from browser."""
    # Mock PlaywrightManager
    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock()

    # Setup mock responses for different evaluate calls
    async def mock_send_request(method, params):
        """Mock send_request to return different responses based on function."""
        if method != "tools/call":
            return {}

        function = params.get("arguments", {}).get("function", "")

        # URL
        if "window.location.href" in function:
            return {"content": [{"type": "text", "text": "https://example.com/test"}]}

        # Cookies
        if "document.cookie" in function:
            return {"content": [{"type": "text", "text": "session=abc123; user=john"}]}

        # localStorage
        if "localStorage" in function:
            return {
                "content": [
                    {"type": "text", "text": '{"key1": "value1", "key2": "value2"}'}
                ]
            }

        # sessionStorage
        if "sessionStorage" in function:
            return {"content": [{"type": "text", "text": '{"tempKey": "tempValue"}'}]}

        # Viewport
        if "innerWidth" in function and "innerHeight" in function:
            return {"content": [{"type": "text", "text": '{"width": 1920, "height": 1080}'}]}

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

    # Verify send_request was called 5 times (URL, cookies, localStorage, sessionStorage, viewport)
    assert mock_playwright.send_request.call_count == 5


@pytest.mark.asyncio
async def test_capture_state_empty_cookies():
    """Test capturing state when there are no cookies."""
    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock()

    async def mock_send_request(method, params):
        """Mock send_request with empty cookies."""
        if method != "tools/call":
            return {}

        function = params.get("arguments", {}).get("function", "")

        if "window.location.href" in function:
            return {"content": [{"type": "text", "text": "https://example.com"}]}
        if "document.cookie" in function:
            return {"content": [{"type": "text", "text": ""}]}  # Empty cookies
        if "localStorage" in function:
            return {"content": [{"type": "text", "text": "{}"}]}
        if "sessionStorage" in function:
            return {"content": [{"type": "text", "text": "{}"}]}
        if "innerWidth" in function and "innerHeight" in function:
            return {"content": [{"type": "text", "text": '{"width": 1024, "height": 768}'}]}

        return {}

    mock_playwright.send_request.side_effect = mock_send_request

    manager = SessionStateManager(mock_playwright)
    snapshot = await manager.capture_state("test-session-456")

    assert snapshot is not None
    cookies = json.loads(snapshot.cookies)
    assert len(cookies) == 0  # No cookies


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
