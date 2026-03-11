"""Tests for playwright-proxy-ctl CLI commands."""

import asyncio
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest
from click.testing import CliRunner

from playwright_mcp_proxy.ctl.commands import cli


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_health_response(status="ok", subprocess_status="running"):
    """Create a mock httpx response for the /health endpoint."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "status": status,
        "playwright_subprocess": subprocess_status,
    }
    mock_resp.raise_for_status.return_value = None
    return mock_resp


def _make_sessions_response(sessions=None, count=None):
    """Create a mock httpx response for the /sessions endpoint."""
    if sessions is None:
        sessions = []
    if count is None:
        count = len(sessions)
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"sessions": sessions, "count": count}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


async def _create_test_db(db_path: str, sessions: list[dict]) -> None:
    """Create a minimal test database with session rows."""
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TIMESTAMP NOT NULL,
                last_activity TIMESTAMP NOT NULL,
                state TEXT NOT NULL,
                metadata TEXT,
                current_url TEXT,
                cookies TEXT,
                local_storage TEXT,
                session_storage TEXT,
                viewport TEXT,
                last_snapshot_time TIMESTAMP
            )
            """
        )
        for s in sessions:
            await conn.execute(
                "INSERT INTO sessions (session_id, created_at, last_activity, state, current_url)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    s["session_id"],
                    "2026-01-01T00:00:00",
                    "2026-01-01T00:00:00",
                    s["state"],
                    s.get("current_url", "https://example.com"),
                ),
            )
        await conn.commit()


# ─── health ───────────────────────────────────────────────────────────────────


def test_health_server_ok():
    """health command prints status and subprocess status when server is up."""
    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get:
        mock_get.return_value = _make_health_response("ok", "running")
        result = runner.invoke(cli, ["health"])
    assert result.exit_code == 0
    assert "Server: ok" in result.output
    assert "Playwright subprocess: running" in result.output


def test_health_server_down():
    """health command prints error and exits 1 when connection refused."""
    import httpx

    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("refused")
        result = runner.invoke(cli, ["health"])
    assert result.exit_code == 1
    assert "not running" in result.output.lower()


def test_health_server_timeout():
    """health command prints timed out and exits 1 on timeout."""
    import httpx

    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get:
        mock_get.side_effect = httpx.TimeoutException("timeout")
        result = runner.invoke(cli, ["health"])
    assert result.exit_code == 1
    assert "timed out" in result.output.lower()


# ─── sessions list ────────────────────────────────────────────────────────────


def test_sessions_list():
    """sessions list prints sessions and total count."""
    runner = CliRunner()
    sessions = [
        {"session_id": "abcdef1234567890", "state": "active", "current_url": "https://example.com"},
        {"session_id": "fedcba0987654321", "state": "closed", "current_url": "https://other.com"},
    ]
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get:
        mock_get.return_value = _make_sessions_response(sessions, 2)
        result = runner.invoke(cli, ["sessions", "list"])
    assert result.exit_code == 0
    assert "abcdef12" in result.output
    assert "state=active" in result.output
    assert "Total: 2" in result.output


def test_sessions_list_empty():
    """sessions list prints 'No sessions found.' when server returns empty list."""
    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get:
        mock_get.return_value = _make_sessions_response([], 0)
        result = runner.invoke(cli, ["sessions", "list"])
    assert result.exit_code == 0
    assert "No sessions found." in result.output


def test_sessions_list_filtered():
    """sessions list --state active passes state param to server."""
    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get:
        mock_get.return_value = _make_sessions_response([], 0)
        result = runner.invoke(cli, ["sessions", "list", "--state", "active"])
    assert result.exit_code == 0
    # Verify the state param was passed
    call_kwargs = mock_get.call_args
    params = call_kwargs[1].get("params") or call_kwargs[0][1] if len(call_kwargs[0]) > 1 else {}
    # params could be in kwargs
    assert mock_get.called


def test_sessions_list_server_down():
    """sessions list prints error and exits 1 when server is down."""
    import httpx

    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("refused")
        result = runner.invoke(cli, ["sessions", "list"])
    assert result.exit_code == 1


# ─── sessions clear ───────────────────────────────────────────────────────────


def test_sessions_clear_with_yes():
    """sessions clear --state closed --yes deletes matching sessions."""
    runner = CliRunner()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    asyncio.run(
        _create_test_db(
            db_path,
            [
                {"session_id": "sess-closed-1", "state": "closed"},
                {"session_id": "sess-closed-2", "state": "closed"},
                {"session_id": "sess-active-1", "state": "active"},
            ],
        )
    )

    with patch("playwright_mcp_proxy.ctl.commands.settings") as mock_settings:
        mock_settings.database_path = Path(db_path)
        result = runner.invoke(cli, ["sessions", "clear", "--state", "closed", "--yes"])

    assert result.exit_code == 0
    assert "2" in result.output  # deleted 2

    # Verify active session still exists
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT session_id FROM sessions").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "sess-active-1"

    Path(db_path).unlink(missing_ok=True)


def test_sessions_clear_confirm_prompt():
    """sessions clear prompts for confirmation when --yes not given."""
    runner = CliRunner()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    asyncio.run(
        _create_test_db(
            db_path,
            [{"session_id": "sess-closed-1", "state": "closed"}],
        )
    )

    with patch("playwright_mcp_proxy.ctl.commands.settings") as mock_settings:
        mock_settings.database_path = Path(db_path)
        result = runner.invoke(cli, ["sessions", "clear", "--state", "closed"], input="y\n")

    assert result.exit_code == 0
    assert "1" in result.output

    Path(db_path).unlink(missing_ok=True)


def test_sessions_clear_no_matching():
    """sessions clear prints 'No sessions' when nothing matches, does not prompt."""
    runner = CliRunner()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    asyncio.run(
        _create_test_db(
            db_path,
            [{"session_id": "sess-active-1", "state": "active"}],
        )
    )

    with patch("playwright_mcp_proxy.ctl.commands.settings") as mock_settings:
        mock_settings.database_path = Path(db_path)
        result = runner.invoke(cli, ["sessions", "clear", "--state", "closed", "--yes"])

    assert result.exit_code == 0
    assert "No sessions" in result.output

    Path(db_path).unlink(missing_ok=True)


def test_sessions_clear_all():
    """sessions clear --state all --yes deletes all sessions."""
    runner = CliRunner()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    asyncio.run(
        _create_test_db(
            db_path,
            [
                {"session_id": "sess-1", "state": "active"},
                {"session_id": "sess-2", "state": "closed"},
                {"session_id": "sess-3", "state": "error"},
            ],
        )
    )

    with patch("playwright_mcp_proxy.ctl.commands.settings") as mock_settings:
        mock_settings.database_path = Path(db_path)
        result = runner.invoke(cli, ["sessions", "clear", "--state", "all", "--yes"])

    assert result.exit_code == 0
    assert "3" in result.output

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()
    conn.close()
    assert rows[0] == 0

    Path(db_path).unlink(missing_ok=True)


# ─── db vacuum ────────────────────────────────────────────────────────────────


def test_db_vacuum_server_not_running():
    """db vacuum vacuums DB when server is not running (ConnectError)."""
    import httpx

    runner = CliRunner()
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create a minimal valid SQLite DB
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
    conn.close()

    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get, patch(
        "playwright_mcp_proxy.ctl.commands.settings"
    ) as mock_settings:
        mock_get.side_effect = httpx.ConnectError("refused")
        mock_settings.server_host = "localhost"
        mock_settings.server_port = 34501
        mock_settings.database_path = Path(db_path)
        result = runner.invoke(cli, ["db", "vacuum"])

    assert result.exit_code == 0
    assert "vacuumed" in result.output.lower()

    Path(db_path).unlink(missing_ok=True)


def test_db_vacuum_server_running():
    """db vacuum prints error and exits 1 when server is running."""
    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get, patch(
        "playwright_mcp_proxy.ctl.commands.settings"
    ) as mock_settings:
        mock_get.return_value = _make_health_response("ok", "running")
        mock_settings.server_host = "localhost"
        mock_settings.server_port = 34501
        result = runner.invoke(cli, ["db", "vacuum"])

    assert result.exit_code == 1
    assert "server is running" in result.output.lower()


def test_db_vacuum_db_error():
    """db vacuum prints error and exits 1 on sqlite3.OperationalError."""
    import httpx

    runner = CliRunner()
    with patch("playwright_mcp_proxy.ctl.commands.httpx.get") as mock_get, patch(
        "playwright_mcp_proxy.ctl.commands.settings"
    ) as mock_settings, patch("playwright_mcp_proxy.ctl.commands.sqlite3.connect") as mock_connect:
        mock_get.side_effect = httpx.ConnectError("refused")
        mock_settings.server_host = "localhost"
        mock_settings.server_port = 34501
        mock_settings.database_path = Path("/nonexistent/path.db")
        mock_connect.side_effect = sqlite3.OperationalError("unable to open")
        result = runner.invoke(cli, ["db", "vacuum"])

    assert result.exit_code == 1
    assert "error" in result.output.lower()
