# Phase 05: CLI Management Tool (playwright-proxy-ctl) - Research

**Researched:** 2026-03-11
**Domain:** Python CLI tooling with Click, async SQLite access, HTTP health checks
**Confidence:** HIGH

## Summary

Phase 5 adds `playwright-proxy-ctl` — an operator-facing CLI for server administration. The tool needs to hit the HTTP API (when server is running) and also read the SQLite database directly (for offline maintenance commands like `db vacuum`). The project already has everything needed: `click` is not yet a dependency, but `httpx` (already in dependencies) covers HTTP calls and `aiosqlite` covers database access.

The standard Python CLI approach for this project is Click 8.x, registered as a `[project.scripts]` entry point in `pyproject.toml`. Since the existing database layer uses `async`/`aiosqlite`, CLI commands that touch the database must bridge sync Click to async via `asyncio.run()`. Commands that only hit the HTTP API are simpler and can stay synchronous using `httpx` (which has a sync client).

**Primary recommendation:** Use Click 8.x with command groups (`sessions`, `db`), register as `playwright-proxy-ctl` entry point, use `httpx` sync client for HTTP commands and `asyncio.run()` + `aiosqlite` for direct DB commands.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| click | >=8.1.0 | CLI framework with groups and decorators | Dominant Python CLI library; composable command groups; auto help pages; used by Flask, Black, and most Python CLIs |
| httpx | >=0.28.0 (already in deps) | HTTP calls to local server | Already a project dependency; has both sync and async clients; familiar API |
| aiosqlite | >=0.21.0 (already in deps) | Direct DB access for offline commands | Already used by Database class; needed for `db vacuum` without server |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio (stdlib) | Python 3.12 | Async event loop | Bridging Click's sync surface to async DB operations |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| click | typer | Typer is nicer (type hints, no decorators) but click is simpler and has no extra dep; adds pydantic dep in full mode |
| click | argparse (stdlib) | No dependency but manual help, no groups |
| httpx | requests | requests is sync-only; httpx already in deps |
| asyncio.run() in each command | asyncclick library | asyncclick avoids boilerplate but adds dep; asyncio.run() is 2 lines |

**Installation:**
```bash
# click is the only new dependency
uv pip install click>=8.1.0
# Add to pyproject.toml dependencies
```

## Architecture Patterns

### Recommended Project Structure
```
playwright_mcp_proxy/
├── ctl/                     # New package for CLI tool
│   ├── __init__.py          # Exports main() entry point
│   └── commands.py          # All CLI commands (sessions group, db group)
```

Or alternatively (if commands grow):
```
playwright_mcp_proxy/
├── ctl/
│   ├── __init__.py          # main() entry point, top-level group
│   ├── sessions.py          # sessions subgroup commands
│   └── db.py                # db subgroup commands
```

Given phase scope (4 commands), a **single `commands.py` with a flat layout is preferred** — keeps implementation in one file, easy to read, avoids premature splitting.

### Pattern 1: Click Command Group Registration
**What:** Top-level group with sub-groups, registered as pyproject.toml script
**When to use:** Hierarchical CLI commands like `ctl sessions list`
**Example:**
```python
# Source: https://click.palletsprojects.com/en/stable/commands/
import click

@click.group()
def cli():
    """playwright-proxy-ctl: Manage the Playwright MCP Proxy server."""
    pass

@cli.group()
def sessions():
    """Session management commands."""
    pass

@sessions.command("list")
@click.option("--state", default=None, help="Filter by state (active, closed, error, ...)")
def sessions_list(state):
    """List all sessions."""
    ...

@sessions.command("clear")
@click.option("--state", default="closed", help="Clear sessions by state")
@click.confirmation_option(prompt="This will delete sessions. Are you sure?")
def sessions_clear(state):
    """Clear sessions from the database."""
    ...

@cli.group()
def db():
    """Database maintenance commands."""
    pass

@db.command("vacuum")
def db_vacuum():
    """Compact the SQLite database file."""
    ...
```

### Pattern 2: Async Bridge for DB Commands
**What:** Wrap async functions with `asyncio.run()` so Click (sync) can call them
**When to use:** Any command that needs direct DB access via aiosqlite
**Example:**
```python
import asyncio
import aiosqlite
from ..config import settings

@db.command("vacuum")
def db_vacuum():
    """Compact the SQLite database (reclaim space from deleted rows)."""
    asyncio.run(_vacuum())

async def _vacuum():
    async with aiosqlite.connect(str(settings.database_path)) as conn:
        await conn.execute("VACUUM")
        await conn.commit()
    click.echo("Database vacuumed successfully.")
```

### Pattern 3: HTTP Client for Server-Dependent Commands
**What:** Use httpx sync client for commands that call the running server
**When to use:** `health` command, any command needing live server state
**Example:**
```python
import httpx
from ..config import settings

@cli.command("health")
def health():
    """Check server health status."""
    url = f"http://{settings.server_host}:{settings.server_port}/health"
    try:
        resp = httpx.get(url, timeout=5.0)
        data = resp.json()
        status = data.get("status", "unknown")
        click.echo(f"Server: {status}")
        click.echo(f"Playwright subprocess: {data.get('playwright_subprocess', 'unknown')}")
    except httpx.ConnectError:
        click.echo("Server is not running (connection refused)", err=True)
        raise SystemExit(1)
    except httpx.TimeoutException:
        click.echo("Server health check timed out", err=True)
        raise SystemExit(1)
```

### Pattern 4: pyproject.toml Entry Point
**What:** Register `playwright-proxy-ctl` as an installable CLI script
**When to use:** Adding a new CLI tool to an existing package
```toml
# Source: https://click.palletsprojects.com/en/stable/entry-points/
[project.scripts]
playwright-proxy-server = "playwright_mcp_proxy.server:main"
playwright-proxy-client = "playwright_mcp_proxy.client:main"
playwright-proxy-ctl = "playwright_mcp_proxy.ctl:main"  # ADD THIS
```

### Anti-Patterns to Avoid
- **Reusing the async `Database` class from `server/`:** The `Database` class holds a persistent connection for the long-running server. CLI commands should use `aiosqlite.connect()` context manager directly — connect, do work, close immediately. Don't import `Database` and call `connect()`/`close()` manually.
- **Calling the HTTP server for `db vacuum`:** VACUUM requires exclusive access. If the server is running, VACUUM will block or fail. The `db vacuum` command should warn if it detects the server is running, or just document that the server should be stopped first.
- **asyncio.run() inside an already-running event loop:** Click commands are called from the terminal (no event loop running), so `asyncio.run()` is correct. Don't use `loop.run_until_complete()`.
- **Hardcoding port 34501:** Always read from `settings.server_port` so environment variable overrides work.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Confirmation prompts | Custom "y/n" input() | `@click.confirmation_option(prompt=...)` or `click.confirm()` | Click handles Ctrl-C, empty input, --yes flag |
| Help text generation | Manual --help logic | Click auto-generates from docstrings and `help=` params | Complete, consistent, handles --help at every level |
| Exit codes | `sys.exit()` in most places | `raise SystemExit(N)` or let Click handle it | Click propagates exit codes correctly |
| Output formatting | f-strings with manual padding | `click.echo()` with styled output via `click.style()` | Works with pipes, --no-color, stderr |

**Key insight:** Click does the heavy lifting for argument parsing, help generation, and error messages. Don't replicate any of it.

## Common Pitfalls

### Pitfall 1: VACUUM Requires Exclusive DB Access
**What goes wrong:** `db vacuum` fails with "database is locked" if the server is running and holding a connection.
**Why it happens:** SQLite's VACUUM needs to write the entire database to a temp file. Any open connection blocks this.
**How to avoid:** Document that server must be stopped before running `db vacuum`. Optionally add a check: try `httpx.get("/health")` — if it responds, warn the user and exit with error unless `--force` flag is passed.
**Warning signs:** `sqlite3.OperationalError: database is locked` in output.

### Pitfall 2: asyncio.run() Called in Wrong Context
**What goes wrong:** `RuntimeError: This event loop is already running` if `asyncio.run()` is called from within an existing event loop.
**Why it happens:** Some test runners (pytest-asyncio with `asyncio_mode=auto`) run in an event loop.
**How to avoid:** In CLI commands, `asyncio.run()` is always correct. In tests for CLI commands, use `CliRunner.invoke()` (synchronous), not `await runner.invoke()`.
**Warning signs:** RuntimeError in test output with async context.

### Pitfall 3: Sessions List with No Server
**What goes wrong:** `sessions list` calls `GET /sessions` but server is down — `httpx.ConnectError` crashes with a stack trace.
**Why it happens:** HTTP calls fail when the target server isn't running.
**How to avoid:** Wrap all `httpx` calls in try/except for `httpx.ConnectError` and `httpx.TimeoutException`. Print a user-friendly message and exit with non-zero code.
**Warning signs:** Ugly traceback instead of "Server not running" message.

### Pitfall 4: sessions clear Deletes Active Sessions
**What goes wrong:** Running `sessions clear` without a state filter wipes active sessions.
**Why it happens:** If default behavior is "delete all closed", but implementation queries all, data loss occurs.
**How to avoid:** Default `--state` to `closed` (safest). Require explicit `--state all` to clear everything. Always show a confirmation prompt. Show count of what will be deleted before confirming.
**Warning signs:** Missing `confirmation_option` or `click.confirm()`.

## Code Examples

Verified patterns from official sources:

### Full CLI Module Structure
```python
# playwright_mcp_proxy/ctl/__init__.py
# Source: https://click.palletsprojects.com/en/stable/entry-points/
from .commands import cli

def main():
    cli()
```

### sessions list (HTTP-based)
```python
# Source: httpx docs + Click docs
@sessions.command("list")
@click.option("--state", default=None, help="Filter by state")
def sessions_list(state: str | None):
    """List all sessions."""
    url = f"http://{settings.server_host}:{settings.server_port}/sessions"
    params = {}
    if state:
        params["state"] = state
    try:
        resp = httpx.get(url, params=params, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        sessions = data.get("sessions", [])
        if not sessions:
            click.echo("No sessions found.")
            return
        for s in sessions:
            click.echo(f"{s['session_id'][:8]}... state={s['state']} url={s.get('current_url', '-')}")
        click.echo(f"\nTotal: {data['count']}")
    except httpx.ConnectError:
        click.echo("Error: server not running", err=True)
        raise SystemExit(1)
```

### sessions clear (direct DB)
```python
# Source: aiosqlite docs + Click confirmation
@sessions.command("clear")
@click.option("--state", default="closed", show_default=True,
              help="State of sessions to clear (closed, error, stale, failed, all)")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def sessions_clear(state: str, yes: bool):
    """Delete sessions from the database by state."""
    asyncio.run(_sessions_clear(state, yes))

async def _sessions_clear(state: str, yes: bool):
    async with aiosqlite.connect(str(settings.database_path)) as conn:
        if state == "all":
            async with conn.execute("SELECT COUNT(*) FROM sessions") as cur:
                row = await cur.fetchone()
                count = row[0]
        else:
            async with conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE state = ?", (state,)
            ) as cur:
                row = await cur.fetchone()
                count = row[0]

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
```

### db vacuum (direct DB, sync sqlite3 preferred)
```python
# Source: https://sqlite.org/lang_vacuum.html
# Note: VACUUM cannot run inside a transaction. Use stdlib sqlite3 (sync) for simplicity.
@db.command("vacuum")
def db_vacuum():
    """Compact the database file (reclaim space from deleted rows).

    The server must NOT be running when this command is executed.
    """
    import sqlite3
    db_path = str(settings.database_path)
    try:
        # Check if server is up first
        try:
            httpx.get(
                f"http://{settings.server_host}:{settings.server_port}/health",
                timeout=1.0
            )
            click.echo(
                "Error: server is running. Stop the server before running db vacuum.",
                err=True,
            )
            raise SystemExit(1)
        except httpx.ConnectError:
            pass  # Server not running — safe to vacuum

        conn = sqlite3.connect(db_path)
        conn.execute("VACUUM")
        conn.close()
        click.echo(f"Database vacuumed: {db_path}")
    except sqlite3.OperationalError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| argparse for CLIs | Click 8.x | ~2015, dominant by 2020 | Groups, decorators, auto-help |
| Synchronous DB ops in CLI | asyncio.run() bridge | Python 3.7+ asyncio.run stable | Allows reusing async code paths |
| requests library for HTTP | httpx | ~2020 | Already in project deps |

**Deprecated/outdated:**
- `asyncio.get_event_loop().run_until_complete()`: Deprecated in Python 3.10, use `asyncio.run()` instead

## Open Questions

1. **Should `sessions clear` go through HTTP API or directly to DB?**
   - What we know: HTTP API has `GET /sessions` (list); no `DELETE /sessions` endpoint exists yet
   - What's unclear: Adding an HTTP endpoint for delete vs. DB-direct
   - Recommendation: Go DB-direct for `clear` (simpler, works offline, consistent with `db vacuum` approach). The server doesn't need to know about deletes of closed/stale sessions.

2. **Should `sessions list` require the server to be running?**
   - What we know: `GET /sessions` endpoint exists on server; DB has sessions table readable directly
   - What's unclear: Offline use case (inspect DB without starting server)
   - Recommendation: Use HTTP API for `list` (simple, always current); document it requires server. For offline inspection, users can use `sqlite3` CLI directly.

3. **Output format for sessions list (table vs. plain lines)?**
   - What we know: Click has no built-in table formatter; `rich` library adds tables but adds dep
   - What's unclear: How dense the session data needs to be
   - Recommendation: Plain `click.echo()` formatted lines; no extra dep. Enough for operational use.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 1.x |
| Config file | pyproject.toml `[tool.pytest.ini_options]` (asyncio_mode = "auto") |
| Quick run command | `uv run pytest tests/test_ctl.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

No formal requirement IDs exist for this phase (new feature). Behavioral requirements derived from phase description:

| Behavior | Test Type | Automated Command | File Exists? |
|----------|-----------|-------------------|-------------|
| `sessions list` returns session list from server | unit (CliRunner + httpx mock) | `uv run pytest tests/test_ctl.py::test_sessions_list -x` | No — Wave 0 |
| `sessions list --state active` filters correctly | unit (CliRunner + httpx mock) | `uv run pytest tests/test_ctl.py::test_sessions_list_filtered -x` | No — Wave 0 |
| `sessions list` with server down prints error, exits 1 | unit (CliRunner + httpx mock) | `uv run pytest tests/test_ctl.py::test_sessions_list_server_down -x` | No — Wave 0 |
| `sessions clear --state closed` deletes only closed sessions | unit (CliRunner + tmp DB) | `uv run pytest tests/test_ctl.py::test_sessions_clear -x` | No — Wave 0 |
| `sessions clear` prompts for confirmation | unit (CliRunner input) | `uv run pytest tests/test_ctl.py::test_sessions_clear_confirm -x` | No — Wave 0 |
| `db vacuum` compacts DB file | unit (CliRunner + tmp DB) | `uv run pytest tests/test_ctl.py::test_db_vacuum -x` | No — Wave 0 |
| `db vacuum` with server running prints error, exits 1 | unit (CliRunner + httpx mock) | `uv run pytest tests/test_ctl.py::test_db_vacuum_server_running -x` | No — Wave 0 |
| `health` shows healthy status from server | unit (CliRunner + httpx mock) | `uv run pytest tests/test_ctl.py::test_health -x` | No — Wave 0 |
| `health` with server down prints error, exits 1 | unit (CliRunner + httpx mock) | `uv run pytest tests/test_ctl.py::test_health_server_down -x` | No — Wave 0 |

### Click Testing Pattern (CliRunner)
```python
# Source: Click testing docs
from click.testing import CliRunner
from playwright_mcp_proxy.ctl.commands import cli

def test_health_server_down():
    runner = CliRunner()
    # Mock httpx.get to raise ConnectError
    result = runner.invoke(cli, ["health"])
    assert result.exit_code == 1
    assert "not running" in result.output
```

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_ctl.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_ctl.py` — covers all CLI command behaviors above
- [ ] `playwright_mcp_proxy/ctl/__init__.py` — package init with `main()`
- [ ] `playwright_mcp_proxy/ctl/commands.py` — CLI command implementations
- [ ] Add `click>=8.1.0` to `pyproject.toml` dependencies
- [ ] Add `playwright-proxy-ctl = "playwright_mcp_proxy.ctl:main"` to `[project.scripts]`

## Sources

### Primary (HIGH confidence)
- [Click 8.3.x official docs — commands/groups](https://click.palletsprojects.com/en/stable/commands/) — command groups, pass_context, registration patterns
- [Click 8.3.x official docs — entry-points](https://click.palletsprojects.com/en/stable/entry-points/) — pyproject.toml script registration
- [SQLite VACUUM official docs](https://sqlite.org/lang_vacuum.html) — VACUUM behavior, exclusivity requirement
- Project source — `playwright_mcp_proxy/` codebase — existing DB layer, HTTP endpoints, config

### Secondary (MEDIUM confidence)
- [httpx PyPI / docs](https://www.python-httpx.org/) — sync client API (already in project deps, confirmed working)
- [Click async patterns](https://github.com/pallets/click/issues/2033) — asyncio.run() wrapper is the standard approach (no native async support in Click 8.x)

### Tertiary (LOW confidence)
- WebSearch results on Click best practices — general guidance, consistent with official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Click 8.x dominance confirmed via official docs; httpx and aiosqlite already in project
- Architecture: HIGH — patterns derived from official Click docs + existing project conventions
- Pitfalls: HIGH — VACUUM exclusivity from official SQLite docs; asyncio.run() behavior from Python 3.12 stdlib; connection error handling from httpx docs
- Test strategy: HIGH — Click's CliRunner is the documented testing approach

**Research date:** 2026-03-11
**Valid until:** 2026-09-11 (stable ecosystem — Click, httpx, aiosqlite all have stable APIs)
