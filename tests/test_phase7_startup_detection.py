"""Tests for Phase 7.2 startup detection and session resumption."""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from playwright_mcp_proxy.config import settings
from playwright_mcp_proxy.database import Database, init_database
from playwright_mcp_proxy.models.database import Session, SessionSnapshot


@pytest.mark.asyncio
async def test_detect_orphaned_sessions_recoverable():
    """Test that recent active sessions are marked as recoverable."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Create an active session (simulating a session from before restart)
        session = Session(
            session_id="test-session-recoverable",
            created_at=datetime.now() - timedelta(minutes=10),
            last_activity=datetime.now() - timedelta(minutes=5),
            state="active",  # Still marked as active
        )
        await db.create_session(session)

        # Create a recent snapshot (within max_session_age)
        snapshot = SessionSnapshot(
            session_id="test-session-recoverable",
            current_url="https://example.com",
            cookies='[{"name": "session", "value": "123"}]',
            local_storage='{"key": "value"}',
            session_storage='{}',
            viewport='{"width": 1920, "height": 1080}',
            snapshot_time=datetime.now() - timedelta(seconds=30),  # 30s ago
        )
        await db.save_session_snapshot(snapshot)

        # Simulate startup detection logic
        active_sessions = await db.list_sessions(state="active")
        assert len(active_sessions) == 1

        latest_snapshot = await db.get_latest_session_snapshot("test-session-recoverable")
        assert latest_snapshot is not None

        age_seconds = (datetime.now() - latest_snapshot.snapshot_time).total_seconds()
        assert age_seconds <= settings.max_session_age

        # Should be marked as recoverable
        await db.update_session_state("test-session-recoverable", "recoverable")

        # Verify state changed
        retrieved = await db.get_session("test-session-recoverable")
        assert retrieved.state == "recoverable"

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_detect_orphaned_sessions_stale():
    """Test that old active sessions are marked as stale."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Create an active session
        session = Session(
            session_id="test-session-stale",
            created_at=datetime.now() - timedelta(days=2),
            last_activity=datetime.now() - timedelta(days=2),
            state="active",
        )
        await db.create_session(session)

        # Create an old snapshot (beyond max_session_age)
        # max_session_age is 24h by default
        snapshot = SessionSnapshot(
            session_id="test-session-stale",
            current_url="https://example.com",
            snapshot_time=datetime.now() - timedelta(days=2),  # 2 days ago
        )
        await db.save_session_snapshot(snapshot)

        # Check age
        latest_snapshot = await db.get_latest_session_snapshot("test-session-stale")
        age_seconds = (datetime.now() - latest_snapshot.snapshot_time).total_seconds()
        assert age_seconds > settings.max_session_age

        # Should be marked as stale
        await db.update_session_state("test-session-stale", "stale")

        retrieved = await db.get_session("test-session-stale")
        assert retrieved.state == "stale"

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_detect_orphaned_sessions_no_snapshot():
    """Test that active sessions with no snapshot are marked as closed."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Create an active session with NO snapshot
        session = Session(
            session_id="test-session-no-snapshot",
            created_at=datetime.now() - timedelta(minutes=10),
            last_activity=datetime.now() - timedelta(minutes=5),
            state="active",
        )
        await db.create_session(session)

        # Verify no snapshot exists
        latest_snapshot = await db.get_latest_session_snapshot("test-session-no-snapshot")
        assert latest_snapshot is None

        # Should be marked as closed
        await db.update_session_state("test-session-no-snapshot", "closed")

        retrieved = await db.get_session("test-session-no-snapshot")
        assert retrieved.state == "closed"

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_list_sessions_by_state():
    """Test listing sessions filtered by state."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Create sessions in different states
        states = ["active", "recoverable", "stale", "closed", "error"]
        for i, state in enumerate(states):
            session = Session(
                session_id=f"test-session-{state}",
                created_at=datetime.now(),
                last_activity=datetime.now(),
                state=state,
            )
            await db.create_session(session)

        # Test filtering by each state
        for state in states:
            sessions = await db.list_sessions(state=state)
            assert len(sessions) == 1
            assert sessions[0].state == state

        # Test listing all sessions (no filter)
        all_sessions = await db.list_sessions()
        assert len(all_sessions) == len(states)

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_session_snapshot_ordering():
    """Test that get_latest_session_snapshot returns the most recent."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Create a session
        session = Session(
            session_id="test-session-ordering",
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state="active",
        )
        await db.create_session(session)

        # Create multiple snapshots at different times
        snapshot1 = SessionSnapshot(
            session_id="test-session-ordering",
            current_url="https://example.com/page1",
            snapshot_time=datetime.now() - timedelta(minutes=10),
        )
        await db.save_session_snapshot(snapshot1)

        snapshot2 = SessionSnapshot(
            session_id="test-session-ordering",
            current_url="https://example.com/page2",
            snapshot_time=datetime.now() - timedelta(minutes=5),
        )
        await db.save_session_snapshot(snapshot2)

        snapshot3 = SessionSnapshot(
            session_id="test-session-ordering",
            current_url="https://example.com/page3",
            snapshot_time=datetime.now(),  # Most recent
        )
        await db.save_session_snapshot(snapshot3)

        # Get latest should return snapshot3
        latest = await db.get_latest_session_snapshot("test-session-ordering")
        assert latest is not None
        assert latest.current_url == "https://example.com/page3"

        # Get all snapshots
        all_snapshots = await db.get_session_snapshots("test-session-ordering")
        assert len(all_snapshots) == 3
        # Should be ordered newest first
        assert all_snapshots[0].current_url == "https://example.com/page3"
        assert all_snapshots[1].current_url == "https://example.com/page2"
        assert all_snapshots[2].current_url == "https://example.com/page1"

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_cleanup_old_snapshots():
    """Test that old snapshots are cleaned up correctly."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name

    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()

        # Create a session
        session = Session(
            session_id="test-session-cleanup",
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state="active",
        )
        await db.create_session(session)

        # Create 15 snapshots
        for i in range(15):
            snapshot = SessionSnapshot(
                session_id="test-session-cleanup",
                current_url=f"https://example.com/page{i}",
                snapshot_time=datetime.now() - timedelta(minutes=15 - i),
            )
            await db.save_session_snapshot(snapshot)

        # Verify all 15 exist
        all_snapshots = await db.get_session_snapshots("test-session-cleanup")
        assert len(all_snapshots) == 15

        # Cleanup, keeping only last 5
        await db.cleanup_old_snapshots("test-session-cleanup", keep_last=5)

        # Should now have only 5 snapshots
        remaining_snapshots = await db.get_session_snapshots("test-session-cleanup")
        assert len(remaining_snapshots) == 5

        # Should be the 5 most recent (page10-14)
        urls = [s.current_url for s in remaining_snapshots]
        assert "https://example.com/page14" in urls
        assert "https://example.com/page13" in urls
        assert "https://example.com/page12" in urls
        assert "https://example.com/page11" in urls
        assert "https://example.com/page10" in urls

        # Old ones should be gone
        assert "https://example.com/page0" not in urls
        assert "https://example.com/page1" not in urls

        await db.close()

    finally:
        Path(db_path).unlink(missing_ok=True)
