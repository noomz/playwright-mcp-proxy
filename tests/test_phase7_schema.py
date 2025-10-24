"""Tests for Phase 7 database schema changes."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from playwright_mcp_proxy.database import Database, init_database
from playwright_mcp_proxy.models.database import Session, SessionSnapshot


@pytest.mark.asyncio
async def test_schema_migration():
    """Test that Phase 7 schema additions don't break existing functionality."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        # Initialize database with new schema
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Test creating session with Phase 7 fields
        session = Session(
            session_id="test-session-123",
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state="active",
            current_url="https://example.com",
            cookies='[{"name": "test", "value": "123"}]',
            local_storage='{"key": "value"}',
            session_storage='{"sessionKey": "sessionValue"}',
            viewport='{"width": 1920, "height": 1080}',
            last_snapshot_time=datetime.now(),
        )
        await db.create_session(session)

        # Verify session was created
        retrieved = await db.get_session("test-session-123")
        assert retrieved is not None
        assert retrieved.session_id == "test-session-123"
        assert retrieved.current_url == "https://example.com"
        assert retrieved.cookies == '[{"name": "test", "value": "123"}]'
        assert retrieved.local_storage == '{"key": "value"}'
        assert retrieved.session_storage == '{"sessionKey": "sessionValue"}'
        assert retrieved.viewport == '{"width": 1920, "height": 1080}'
        assert retrieved.last_snapshot_time is not None

        # Test creating session without Phase 7 fields (backward compatibility)
        session_minimal = Session(
            session_id="test-session-minimal",
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state="active",
        )
        await db.create_session(session_minimal)

        retrieved_minimal = await db.get_session("test-session-minimal")
        assert retrieved_minimal is not None
        assert retrieved_minimal.current_url is None
        assert retrieved_minimal.cookies is None

        await db.close()

    finally:
        # Cleanup
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_new_session_states():
    """Test that new session states (recoverable, stale, failed) work."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Test each new state
        for state in ["recoverable", "stale", "failed"]:
            session = Session(
                session_id=f"test-session-{state}",
                created_at=datetime.now(),
                last_activity=datetime.now(),
                state=state,
            )
            await db.create_session(session)

            retrieved = await db.get_session(f"test-session-{state}")
            assert retrieved is not None
            assert retrieved.state == state

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_session_snapshots_table_exists():
    """Test that session_snapshots table was created."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Check that session_snapshots table exists
        async with db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_snapshots'"
        ) as cursor:
            result = await cursor.fetchone()
            assert result is not None
            assert result[0] == "session_snapshots"

        # Check indexes exist
        async with db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_session_snapshots_session'"
        ) as cursor:
            result = await cursor.fetchone()
            assert result is not None

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)
