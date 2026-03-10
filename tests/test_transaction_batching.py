"""Tests for transaction batching behavior in Database operations."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiosqlite
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


@pytest.fixture
async def db_with_session(db):
    """Database with a pre-created session and request for response tests."""
    session = Session(
        session_id="test-session-batch",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    request = Request(
        ref_id="test-ref-batch",
        session_id="test-session-batch",
        tool_name="browser_snapshot",
        params="{}",
        timestamp=datetime.now(),
    )
    await db.create_request(request)

    return db


@pytest.mark.asyncio
async def test_no_commit_methods_do_not_commit(db_with_session):
    """
    After calling create_response_no_commit, the row should NOT be visible
    from a second independent connection (uncommitted).
    After calling db.commit(), the row IS visible.
    """
    db = db_with_session
    db_path = db.db_path

    response = Response(
        ref_id="test-ref-batch",
        status="success",
        result='{"tool": "browser_snapshot"}',
        page_snapshot="- heading 'Test'",
        timestamp=datetime.now(),
    )

    # Call the no-commit variant - row should NOT be visible externally
    await db.create_response_no_commit(response)

    # Open a second connection and verify row is NOT visible (uncommitted)
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM responses WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None, "Row should NOT be visible before commit"

    # Now commit explicitly
    await db.commit()

    # Verify row IS now visible from second connection
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM responses WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None, "Row SHOULD be visible after commit"
            assert row["status"] == "success"


@pytest.mark.asyncio
async def test_post_rpc_writes_batch_committed(db_with_session):
    """
    Calling create_response_no_commit + update_session_activity_no_commit +
    create_console_logs_batch_no_commit followed by a single commit() makes
    all rows visible atomically.
    """
    db = db_with_session
    db_path = db.db_path

    response = Response(
        ref_id="test-ref-batch",
        status="success",
        result='{"tool": "browser_snapshot"}',
        page_snapshot="- heading 'BatchTest'",
        timestamp=datetime.now(),
    )
    logs = [
        ConsoleLog(
            ref_id="test-ref-batch",
            level="info",
            message="Page loaded",
            timestamp=datetime.now(),
        )
    ]

    # All three no-commit calls
    await db.create_response_no_commit(response)
    await db.update_session_activity_no_commit("test-session-batch")
    await db.create_console_logs_batch_no_commit(logs)

    # Verify nothing is visible yet from a second connection
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM responses WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None, "Response row should not be visible before commit"

        async with second_conn.execute(
            "SELECT COUNT(*) as count FROM console_logs WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            count_row = await cursor.fetchone()
            assert count_row["count"] == 0, "Console logs should not be visible before commit"

    # Single explicit commit
    await db.commit()

    # Now all rows should be visible
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM responses WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None, "Response row should be visible after commit"

        async with second_conn.execute(
            "SELECT COUNT(*) as count FROM console_logs WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            count_row = await cursor.fetchone()
            assert count_row["count"] == 1, "Console logs should be visible after commit"


@pytest.mark.asyncio
async def test_request_committed_before_rpc(db_with_session):
    """
    create_request still commits internally (row visible from second connection
    immediately after call, without explicit commit).
    """
    db = db_with_session
    db_path = db.db_path

    # create a second request (beyond the one already created by the fixture)
    new_request = Request(
        ref_id="test-ref-audit-trail",
        session_id="test-session-batch",
        tool_name="browser_navigate",
        params='{"url": "https://example.com"}',
        timestamp=datetime.now(),
    )

    await db.create_request(new_request)

    # Immediately check from a second connection (no explicit commit needed)
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM requests WHERE ref_id = ?", ("test-ref-audit-trail",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None, "Request row SHOULD be immediately visible (internal commit)"
            assert row["tool_name"] == "browser_navigate"


@pytest.mark.asyncio
async def test_request_durable_on_rpc_failure(db_with_session):
    """
    After create_request, even if subsequent operations raise, the request row
    is still in the DB.
    """
    db = db_with_session
    db_path = db.db_path

    failure_request = Request(
        ref_id="test-ref-durable",
        session_id="test-session-batch",
        tool_name="browser_click",
        params='{"selector": "#btn"}',
        timestamp=datetime.now(),
    )

    await db.create_request(failure_request)

    # Simulate RPC failure by raising an exception
    try:
        raise RuntimeError("Simulated Playwright RPC failure")
    except RuntimeError:
        pass  # Don't commit anything else

    # Request should still be visible (durability)
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM requests WHERE ref_id = ?", ("test-ref-durable",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None, "Request row must be durable even after RPC failure"
            assert row["tool_name"] == "browser_click"


@pytest.mark.asyncio
async def test_error_path_batch_committed(db_with_session):
    """
    create_response_no_commit (error) + update_session_state_no_commit followed
    by commit() makes both the error response and state='error' visible.
    """
    db = db_with_session
    db_path = db.db_path

    error_response = Response(
        ref_id="test-ref-batch",
        status="error",
        error_message="Playwright RPC timed out",
        timestamp=datetime.now(),
    )

    # Error path: no-commit variants
    await db.create_response_no_commit(error_response)
    await db.update_session_state_no_commit("test-session-batch", "error")

    # Verify nothing visible yet
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM responses WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is None, "Error response should not be visible before commit"

        async with second_conn.execute(
            "SELECT state FROM sessions WHERE session_id = ?", ("test-session-batch",)
        ) as cursor:
            state_row = await cursor.fetchone()
            # Session was committed by create_session in fixture, state is 'active'
            assert state_row["state"] == "active", "Session state should still be 'active' before commit"

    # Single explicit commit
    await db.commit()

    # Both should now be visible
    async with aiosqlite.connect(db_path) as second_conn:
        second_conn.row_factory = aiosqlite.Row
        async with second_conn.execute(
            "SELECT * FROM responses WHERE ref_id = ?", ("test-ref-batch",)
        ) as cursor:
            row = await cursor.fetchone()
            assert row is not None, "Error response should be visible after commit"
            assert row["status"] == "error"

        async with second_conn.execute(
            "SELECT state FROM sessions WHERE session_id = ?", ("test-session-batch",)
        ) as cursor:
            state_row = await cursor.fetchone()
            assert state_row["state"] == "error", "Session state should be 'error' after commit"


@pytest.mark.asyncio
async def test_commit_count_success_path(db_with_session):
    """
    Verify that the success path issues exactly 2 commits:
    one from create_request (internal), one explicit post-RPC commit.

    This test spies on conn.commit to count calls made during the
    create_request + (no-commit variants) + explicit commit sequence.
    """
    db = db_with_session

    # We want to count commits from this point
    commit_calls = []
    original_commit = db.conn.commit

    async def counting_commit():
        commit_calls.append(1)
        return await original_commit()

    # Patch the connection's commit method
    db.conn.commit = counting_commit

    try:
        # COMMIT 1: create_request (internal)
        request_for_count = Request(
            ref_id="test-ref-count",
            session_id="test-session-batch",
            tool_name="browser_snapshot",
            params="{}",
            timestamp=datetime.now(),
        )
        await db.create_request(request_for_count)

        # No-commit variants (should NOT call commit)
        response = Response(
            ref_id="test-ref-count",
            status="success",
            result='{"tool": "browser_snapshot"}',
            page_snapshot="- heading 'Count'",
            timestamp=datetime.now(),
        )
        logs = [
            ConsoleLog(
                ref_id="test-ref-count",
                level="info",
                message="Loaded",
                timestamp=datetime.now(),
            )
        ]
        await db.create_response_no_commit(response)
        await db.update_session_activity_no_commit("test-session-batch")
        await db.create_console_logs_batch_no_commit(logs)

        # COMMIT 2: explicit post-RPC commit
        await db.commit()

    finally:
        # Restore original commit
        db.conn.commit = original_commit

    assert len(commit_calls) == 2, (
        f"Expected exactly 2 commits in success path, got {len(commit_calls)}"
    )
