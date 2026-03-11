"""CLI commands for playwright-proxy-ctl."""

import asyncio
import sqlite3

import aiosqlite
import click
import httpx

from ..config import settings


@click.group()
def cli() -> None:
    """playwright-proxy-ctl: Manage the Playwright MCP Proxy server."""


# ─── health ───────────────────────────────────────────────────────────────────


@cli.command("health")
def health() -> None:
    """Check the server health status."""
    url = f"http://{settings.server_host}:{settings.server_port}/health"
    try:
        resp = httpx.get(url, timeout=5.0)
        data = resp.json()
        click.echo(f"Server: {data.get('status', 'unknown')}")
        click.echo(f"Playwright subprocess: {data.get('playwright_subprocess', 'unknown')}")
    except httpx.ConnectError:
        click.echo("Server is not running (connection refused)", err=True)
        raise SystemExit(1)
    except httpx.TimeoutException:
        click.echo("Server health check timed out", err=True)
        raise SystemExit(1)


# ─── sessions ─────────────────────────────────────────────────────────────────


@cli.group()
def sessions() -> None:
    """Session management commands."""


@sessions.command("list")
@click.option("--state", default=None, help="Filter by state (active, closed, error, ...)")
def sessions_list(state: str | None) -> None:
    """List all sessions from the running server."""
    url = f"http://{settings.server_host}:{settings.server_port}/sessions"
    params: dict[str, str] = {}
    if state:
        params["state"] = state
    try:
        resp = httpx.get(url, params=params, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        session_list = data.get("sessions", [])
        if not session_list:
            click.echo("No sessions found.")
            return
        for s in session_list:
            sid = s.get("session_id", "")
            truncated = f"{sid[:8]}..." if len(sid) > 8 else sid
            s_state = s.get("state", "unknown")
            url_val = s.get("current_url", "-")
            click.echo(f"{truncated} state={s_state} url={url_val}")
        click.echo(f"\nTotal: {data.get('count', len(session_list))}")
    except httpx.ConnectError:
        click.echo("Error: server not running (connection refused)", err=True)
        raise SystemExit(1)
    except httpx.TimeoutException:
        click.echo("Error: server health check timed out", err=True)
        raise SystemExit(1)


@sessions.command("clear")
@click.option(
    "--state",
    default="closed",
    show_default=True,
    help="State of sessions to clear (closed, error, stale, failed, all)",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def sessions_clear(state: str, yes: bool) -> None:
    """Delete sessions from the database by state."""
    asyncio.run(_sessions_clear(state, yes))


async def _sessions_clear(state: str, yes: bool) -> None:
    """Async implementation of sessions clear."""
    async with aiosqlite.connect(str(settings.database_path)) as conn:
        if state == "all":
            async with conn.execute("SELECT COUNT(*) FROM sessions") as cur:
                row = await cur.fetchone()
                count = row[0] if row else 0
        else:
            async with conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE state = ?", (state,)
            ) as cur:
                row = await cur.fetchone()
                count = row[0] if row else 0

        if count == 0:
            click.echo(f"No sessions with state '{state}' found.")
            return

        if not yes:
            click.confirm(f"Delete {count} session(s) with state '{state}'?", abort=True)

        if state == "all":
            await conn.execute("DELETE FROM sessions")
        else:
            await conn.execute("DELETE FROM sessions WHERE state = ?", (state,))
        await conn.commit()
        click.echo(f"Deleted {count} session(s).")


# ─── db ───────────────────────────────────────────────────────────────────────


@cli.group()
def db() -> None:
    """Database maintenance commands."""


@db.command("vacuum")
def db_vacuum() -> None:
    """Compact the database file (reclaim space from deleted rows).

    The server must NOT be running when this command is executed.
    """
    db_path = str(settings.database_path)
    try:
        # Check if server is up — VACUUM requires exclusive access
        try:
            httpx.get(
                f"http://{settings.server_host}:{settings.server_port}/health",
                timeout=1.0,
            )
            click.echo(
                "Error: server is running. Stop the server before running db vacuum.",
                err=True,
            )
            raise SystemExit(1)
        except httpx.ConnectError:
            pass  # Server not running — safe to vacuum
        except httpx.TimeoutException:
            pass  # Server not responding — treat as not running

        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()
        click.echo(f"Database vacuumed: {db_path}")
    except sqlite3.OperationalError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
