"""Tests for sleep recovery: orphan Chrome cleanup, sleep detection, cursor purge."""

import os
import signal
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import psutil
import pytest

from playwright_mcp_proxy.server.playwright_manager import PlaywrightManager


def test_find_orphan_chrome_processes_with_mock():
    """Test that _find_orphan_chrome_pids finds Chrome processes matching mcp-chrome marker."""
    manager = PlaywrightManager()

    fake_procs = [
        {"pid": 100, "cmdline": ["/usr/bin/chrome", "--user-data-dir=/home/user/.cache/ms-playwright/mcp-chrome"]},
        {"pid": 200, "cmdline": ["/usr/bin/chrome", "--profile-dir=default"]},
        {"pid": 300, "cmdline": ["node", "playwright-mcp"]},
        {"pid": 400, "cmdline": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--user-data-dir=/Users/u/Library/Caches/ms-playwright/mcp-chrome", "--remote-debugging-port=9222"]},
    ]

    def mock_process_iter(attrs):
        for proc_info in fake_procs:
            mock_proc = MagicMock()
            mock_proc.info = proc_info
            yield mock_proc

    with patch("psutil.process_iter", side_effect=mock_process_iter):
        pids = manager._find_orphan_chrome_pids()

    assert sorted(pids) == [100, 400]


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


def test_get_chrome_lock_path_darwin():
    """Test lock path on macOS."""
    with patch("sys.platform", "darwin"):
        path = PlaywrightManager._get_chrome_lock_path()
    assert "Library/Caches/ms-playwright/mcp-chrome/SingletonLock" in str(path)


def test_get_chrome_lock_path_linux():
    """Test lock path on Linux."""
    with patch("sys.platform", "linux"):
        path = PlaywrightManager._get_chrome_lock_path()
    assert ".cache/ms-playwright/mcp-chrome/SingletonLock" in str(path)


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
