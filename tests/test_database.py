"""Tests for database layer."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from playwright_mcp_proxy.database import Database, init_database
from playwright_mcp_proxy.models.database import ConsoleLog, Request, Response, Session


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Initialize database
    await init_database(db_path)

    # Create database instance
    database = Database(db_path)
    await database.connect()

    yield database

    # Cleanup
    await database.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_create_and_get_session(db):
    """Test creating and retrieving a session."""
    session = Session(
        session_id="test-session-1",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )

    await db.create_session(session)

    retrieved = await db.get_session("test-session-1")
    assert retrieved is not None
    assert retrieved.session_id == "test-session-1"
    assert retrieved.state == "active"


@pytest.mark.asyncio
async def test_update_session_activity(db):
    """Test updating session last activity."""
    session = Session(
        session_id="test-session-2",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )

    await db.create_session(session)

    # Update activity
    await db.update_session_activity("test-session-2")

    retrieved = await db.get_session("test-session-2")
    assert retrieved is not None
    assert retrieved.last_activity > session.last_activity


@pytest.mark.asyncio
async def test_create_and_get_request(db):
    """Test creating and retrieving a request."""
    # Create session first
    session = Session(
        session_id="test-session-3",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    # Create request
    request = Request(
        ref_id="test-ref-1",
        session_id="test-session-3",
        tool_name="browser_navigate",
        params='{"url": "https://example.com"}',
        timestamp=datetime.now(),
    )

    await db.create_request(request)

    retrieved = await db.get_request("test-ref-1")
    assert retrieved is not None
    assert retrieved.ref_id == "test-ref-1"
    assert retrieved.tool_name == "browser_navigate"


@pytest.mark.asyncio
async def test_create_and_get_response(db):
    """Test creating and retrieving a response."""
    # Create session and request first
    session = Session(
        session_id="test-session-4",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    request = Request(
        ref_id="test-ref-2",
        session_id="test-session-4",
        tool_name="browser_snapshot",
        params="{}",
        timestamp=datetime.now(),
    )
    await db.create_request(request)

    # Create response
    response = Response(
        ref_id="test-ref-2",
        status="success",
        result='{"content": [...]}',
        page_snapshot="- heading 'Example'",
        timestamp=datetime.now(),
    )

    await db.create_response(response)

    retrieved = await db.get_response("test-ref-2")
    assert retrieved is not None
    assert retrieved.ref_id == "test-ref-2"
    assert retrieved.status == "success"
    assert retrieved.page_snapshot == "- heading 'Example'"


@pytest.mark.asyncio
async def test_console_logs(db):
    """Test creating and retrieving console logs."""
    # Create session, request, and response first
    session = Session(
        session_id="test-session-5",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    request = Request(
        ref_id="test-ref-3",
        session_id="test-session-5",
        tool_name="browser_console_messages",
        params="{}",
        timestamp=datetime.now(),
    )
    await db.create_request(request)

    response = Response(
        ref_id="test-ref-3",
        status="success",
        timestamp=datetime.now(),
    )
    await db.create_response(response)

    # Create console logs
    logs = [
        ConsoleLog(
            ref_id="test-ref-3",
            level="info",
            message="Page loaded",
            timestamp=datetime.now(),
        ),
        ConsoleLog(
            ref_id="test-ref-3",
            level="error",
            message="Script error",
            timestamp=datetime.now(),
        ),
    ]

    await db.create_console_logs_batch(logs)

    # Get all logs
    all_logs = await db.get_console_logs("test-ref-3")
    assert len(all_logs) == 2

    # Get error logs only
    error_logs = await db.get_console_logs("test-ref-3", level="error")
    assert len(error_logs) == 1
    assert error_logs[0].level == "error"

    # Get error count
    error_count = await db.get_console_error_count("test-ref-3")
    assert error_count == 1


@pytest.mark.asyncio
async def test_list_sessions(db):
    """Test listing sessions."""
    # Create multiple sessions
    for i in range(3):
        session = Session(
            session_id=f"test-session-{i}",
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state="active" if i < 2 else "closed",
        )
        await db.create_session(session)

    # List all sessions
    all_sessions = await db.list_sessions()
    assert len(all_sessions) == 3

    # List active sessions only
    active_sessions = await db.list_sessions(state="active")
    assert len(active_sessions) == 2

    # List closed sessions only
    closed_sessions = await db.list_sessions(state="closed")
    assert len(closed_sessions) == 1
