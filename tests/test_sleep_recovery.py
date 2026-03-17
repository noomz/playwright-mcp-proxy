"""Tests for sleep recovery: orphan Chrome cleanup, sleep detection, cursor purge."""

import signal
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from playwright_mcp_proxy.database import Database, init_database
from playwright_mcp_proxy.models.database import DiffCursor
from playwright_mcp_proxy.server.playwright_manager import PlaywrightManager


def test_find_orphan_chrome_processes_with_mock():
    """Test that _find_orphan_chrome_pids finds Chrome processes matching the proxy's user-data-dir."""
    manager = PlaywrightManager()

    fake_procs = [
        {"pid": 100, "cmdline": ["/usr/bin/chrome", "--user-data-dir=/home/user/.cache/playwright-mcp-proxy/chrome-profile"]},
        {"pid": 200, "cmdline": ["/usr/bin/chrome", "--profile-dir=default"]},
        {"pid": 300, "cmdline": ["node", "playwright-mcp"]},
        {"pid": 400, "cmdline": ["/usr/bin/chrome", "--user-data-dir=/Users/u/Library/Caches/ms-playwright/mcp-chrome"]},
    ]

    def mock_process_iter(attrs):
        for proc_info in fake_procs:
            mock_proc = MagicMock()
            mock_proc.info = proc_info
            yield mock_proc

    # The marker comes from settings.playwright_user_data_dir
    marker = manager._get_user_data_dir_marker()
    with patch("psutil.process_iter", side_effect=mock_process_iter):
        pids = manager._find_orphan_chrome_pids()

    # Only PIDs matching the proxy's configured user-data-dir marker
    assert all(marker in " ".join(fake_procs[i]["cmdline"]) for i in range(len(fake_procs)) if fake_procs[i]["pid"] in pids)


def test_kill_orphan_chrome_calls_kill():
    """Test that _kill_orphan_chrome kills found processes and removes lock."""
    manager = PlaywrightManager()

    with patch.object(manager, "_find_orphan_chrome_pids", return_value=[12345, 12346]):
        with patch("os.kill") as mock_kill:
            with patch.object(type(manager), "_get_chrome_lock_path") as mock_lock:
                mock_path = MagicMock()
                mock_path.exists.return_value = True
                mock_lock.return_value = mock_path
                killed = manager._kill_orphan_chrome()

    assert killed == 2
    assert mock_kill.call_count == 2
    mock_kill.assert_any_call(12345, signal.SIGTERM)
    mock_kill.assert_any_call(12346, signal.SIGTERM)
    mock_path.unlink.assert_called_once()


def test_get_chrome_lock_path_custom():
    """Test lock path uses custom user-data-dir when configured."""
    manager = PlaywrightManager()
    # Default config has a custom user-data-dir set
    path = manager._get_chrome_lock_path()
    assert "playwright-mcp-proxy" in str(path)
    assert str(path).endswith("SingletonLock")


def test_get_chrome_lock_path_fallback():
    """Test lock path falls back to default mcp-chrome when user-data-dir is None."""
    manager = PlaywrightManager()
    with patch("playwright_mcp_proxy.server.playwright_manager.settings") as mock_settings:
        mock_settings.playwright_user_data_dir = None
        path = manager._get_chrome_lock_path()
    assert "ms-playwright/mcp-chrome/SingletonLock" in str(path)


@pytest.mark.asyncio
async def test_start_calls_kill_orphan_chrome():
    """Test that start() calls _kill_orphan_chrome before spawning subprocess."""
    manager = PlaywrightManager()
    kill_called = False

    def mock_kill():
        nonlocal kill_called
        kill_called = True
        return 0

    manager._kill_orphan_chrome = mock_kill

    with patch("asyncio.create_subprocess_exec", side_effect=Exception("stop here")):
        with pytest.raises(Exception, match="stop here"):
            await manager.start()

    assert kill_called


def test_is_sleep_jump_true():
    """Test that a large time jump is detected as sleep."""
    assert PlaywrightManager._is_sleep_jump(
        last_check=1000.0, now=1300.0, interval=30
    )


def test_is_sleep_jump_false_normal():
    """Test that normal elapsed time is not detected as sleep."""
    assert not PlaywrightManager._is_sleep_jump(
        last_check=1000.0, now=1032.0, interval=30
    )


def test_is_sleep_jump_false_borderline():
    """Test that borderline elapsed time (exactly 3x) is not detected."""
    assert not PlaywrightManager._is_sleep_jump(
        last_check=1000.0, now=1090.0, interval=30
    )


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    await init_database(db_path)
    database = Database(db_path)
    await database.connect()
    yield database
    await database.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_delete_all_diff_cursors(db):
    """Test that delete_all_diff_cursors removes all cursors."""
    for i in range(3):
        cursor = DiffCursor(
            ref_id=f"ref-{i}",
            cursor_position=100,
            last_snapshot_hash=f"hash-{i}",
            last_read=datetime.now(),
        )
        await db.upsert_diff_cursor(cursor)

    for i in range(3):
        assert await db.get_diff_cursor(f"ref-{i}") is not None

    count = await db.delete_all_diff_cursors()
    assert count == 3

    for i in range(3):
        assert await db.get_diff_cursor(f"ref-{i}") is None


@pytest.mark.asyncio
async def test_delete_all_diff_cursors_empty(db):
    """Test that delete_all_diff_cursors returns 0 when no cursors exist."""
    count = await db.delete_all_diff_cursors()
    assert count == 0


def test_on_restart_callback_registered():
    """Test that PlaywrightManager accepts and stores an on_restart callback."""
    async def my_callback():
        pass

    manager = PlaywrightManager(on_restart=my_callback)
    assert manager._on_restart is my_callback
