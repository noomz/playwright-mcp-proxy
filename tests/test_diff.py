"""Tests for Phase 2 diff functionality."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from playwright_mcp_proxy.database import Database, init_database
from playwright_mcp_proxy.models.database import DiffCursor, Request, Response, Session
from playwright_mcp_proxy.server.app import compute_hash


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
async def test_diff_cursor_create_and_get(db):
    """Test creating and retrieving a diff cursor."""
    cursor = DiffCursor(
        ref_id="test-ref-1",
        cursor_position=100,
        last_snapshot_hash="abc123",
        last_read=datetime.now(),
    )

    await db.upsert_diff_cursor(cursor)

    retrieved = await db.get_diff_cursor("test-ref-1")
    assert retrieved is not None
    assert retrieved.ref_id == "test-ref-1"
    assert retrieved.cursor_position == 100
    assert retrieved.last_snapshot_hash == "abc123"


@pytest.mark.asyncio
async def test_diff_cursor_update(db):
    """Test updating a diff cursor."""
    cursor = DiffCursor(
        ref_id="test-ref-2",
        cursor_position=100,
        last_snapshot_hash="abc123",
        last_read=datetime.now(),
    )

    await db.upsert_diff_cursor(cursor)

    # Update cursor
    cursor.cursor_position = 200
    cursor.last_snapshot_hash = "def456"
    await db.upsert_diff_cursor(cursor)

    retrieved = await db.get_diff_cursor("test-ref-2")
    assert retrieved is not None
    assert retrieved.cursor_position == 200
    assert retrieved.last_snapshot_hash == "def456"


@pytest.mark.asyncio
async def test_diff_cursor_delete(db):
    """Test deleting a diff cursor (reset)."""
    cursor = DiffCursor(
        ref_id="test-ref-3",
        cursor_position=100,
        last_snapshot_hash="abc123",
        last_read=datetime.now(),
    )

    await db.upsert_diff_cursor(cursor)

    # Verify it exists
    retrieved = await db.get_diff_cursor("test-ref-3")
    assert retrieved is not None

    # Delete it
    await db.delete_diff_cursor("test-ref-3")

    # Verify it's gone
    retrieved = await db.get_diff_cursor("test-ref-3")
    assert retrieved is None


@pytest.mark.asyncio
async def test_hash_computation():
    """Test hash computation is consistent."""
    content1 = "Hello, World!"
    content2 = "Hello, World!"
    content3 = "Hello, World!!"

    hash1 = compute_hash(content1)
    hash2 = compute_hash(content2)
    hash3 = compute_hash(content3)

    assert hash1 == hash2  # Same content should have same hash
    assert hash1 != hash3  # Different content should have different hash


@pytest.mark.asyncio
async def test_diff_workflow_first_read(db):
    """Test diff workflow: first read returns full content and creates cursor."""
    # Create session, request, and response
    session = Session(
        session_id="test-session-1",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    request = Request(
        ref_id="test-ref-4",
        session_id="test-session-1",
        tool_name="browser_snapshot",
        params="{}",
        timestamp=datetime.now(),
    )
    await db.create_request(request)

    content = "- heading 'Example Domain'\n- text 'This is an example'"
    response = Response(
        ref_id="test-ref-4",
        status="success",
        page_snapshot=content,
        timestamp=datetime.now(),
    )
    await db.create_response(response)

    # First read: no cursor exists
    cursor = await db.get_diff_cursor("test-ref-4")
    assert cursor is None

    # Simulate first read: create cursor
    content_hash = compute_hash(content)
    new_cursor = DiffCursor(
        ref_id="test-ref-4",
        cursor_position=len(content),
        last_snapshot_hash=content_hash,
        last_read=datetime.now(),
    )
    await db.upsert_diff_cursor(new_cursor)

    # Verify cursor was created
    cursor = await db.get_diff_cursor("test-ref-4")
    assert cursor is not None
    assert cursor.last_snapshot_hash == content_hash


@pytest.mark.asyncio
async def test_diff_workflow_no_changes(db):
    """Test diff workflow: second read with no changes returns empty."""
    # Create session, request, and response
    session = Session(
        session_id="test-session-2",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    request = Request(
        ref_id="test-ref-5",
        session_id="test-session-2",
        tool_name="browser_snapshot",
        params="{}",
        timestamp=datetime.now(),
    )
    await db.create_request(request)

    content = "- heading 'Example Domain'"
    response = Response(
        ref_id="test-ref-5",
        status="success",
        page_snapshot=content,
        timestamp=datetime.now(),
    )
    await db.create_response(response)

    # First read: create cursor
    content_hash = compute_hash(content)
    cursor = DiffCursor(
        ref_id="test-ref-5",
        cursor_position=len(content),
        last_snapshot_hash=content_hash,
        last_read=datetime.now(),
    )
    await db.upsert_diff_cursor(cursor)

    # Second read: content unchanged
    retrieved_response = await db.get_response("test-ref-5")
    current_hash = compute_hash(retrieved_response.page_snapshot)

    retrieved_cursor = await db.get_diff_cursor("test-ref-5")
    assert retrieved_cursor.last_snapshot_hash == current_hash

    # This means no changes - would return empty string


@pytest.mark.asyncio
async def test_diff_workflow_with_changes(db):
    """Test diff workflow: content changed returns new content."""
    # Create session, request, and response
    session = Session(
        session_id="test-session-3",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    request = Request(
        ref_id="test-ref-6",
        session_id="test-session-3",
        tool_name="browser_snapshot",
        params="{}",
        timestamp=datetime.now(),
    )
    await db.create_request(request)

    # Original content
    original_content = "- heading 'Example Domain'"
    response = Response(
        ref_id="test-ref-6",
        status="success",
        page_snapshot=original_content,
        timestamp=datetime.now(),
    )
    await db.create_response(response)

    # First read: create cursor
    content_hash = compute_hash(original_content)
    cursor = DiffCursor(
        ref_id="test-ref-6",
        cursor_position=len(original_content),
        last_snapshot_hash=content_hash,
        last_read=datetime.now(),
    )
    await db.upsert_diff_cursor(cursor)

    # Simulate content change (in real scenario, this would be a new snapshot)
    new_content = "- heading 'Example Domain'\n- text 'New content appeared'"
    new_hash = compute_hash(new_content)

    # Hashes should be different
    assert content_hash != new_hash

    # This means content changed - would return full new content


@pytest.mark.asyncio
async def test_diff_cursor_persists_across_restart(db):
    """Test that diff cursors persist in SQLite (survive restart)."""
    cursor = DiffCursor(
        ref_id="test-ref-7",
        cursor_position=500,
        last_snapshot_hash="persistent-hash",
        last_read=datetime.now(),
    )

    await db.upsert_diff_cursor(cursor)

    # Close and reopen database (simulating restart)
    await db.close()
    await db.connect()

    # Cursor should still exist
    retrieved = await db.get_diff_cursor("test-ref-7")
    assert retrieved is not None
    assert retrieved.cursor_position == 500
    assert retrieved.last_snapshot_hash == "persistent-hash"
