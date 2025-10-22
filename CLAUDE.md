# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Playwright MCP Proxy is a two-component Python system that wraps Playwright's MCP server with persistent storage and session management. It consists of:

1. **MCP Client** (`playwright_mcp_proxy/client/`) - stdio-based MCP server that exposes tools to upstream clients
2. **HTTP Server** (`playwright_mcp_proxy/server/`) - FastAPI server that manages a Playwright subprocess and persists data to SQLite

Data flows: `MCP Client (stdio) → HTTP Server (localhost:34501) → Playwright subprocess (stdio) → Browser`

## Architecture Essentials

### Two-Component Communication
- **MCP Client** receives stdio MCP calls from upstream (e.g., Claude Desktop)
- Translates to HTTP/JSON requests to local HTTP server (port 34501)
- Returns only **metadata + ref_id** (Phase 1 response policy), not full payloads
- Full content retrieved later via `get_content(ref_id)`

### Subprocess Management (server/playwright_manager.py)
- HTTP server spawns and owns `npx @playwright/mcp@latest` subprocess
- Health monitoring: 30s ping intervals, 3-strike failure detection
- Auto-restart: max 3 attempts per 5min with exponential backoff (1s, 2s, 4s)
- Graceful shutdown: browser_close → SIGTERM → wait → SIGKILL

### Persistence Strategy
All requests/responses stored as **blobs** in SQLite:
- `responses.result`: JSON string (unparsed, exact bytes from Playwright)
- `responses.page_snapshot`: TEXT (raw accessibility tree, preserving formatting)
- `responses.console_logs`: JSON string (backup/redundancy)
- **No transformation on write** - enables Phase 2 diff by comparing raw strings

### Diff-Based Content (Phase 2)
`get_content(ref_id)` returns only changes since last read using SHA256 hash comparison:
- First read: returns full content, creates cursor in `diff_cursors` table
- Subsequent reads: empty string if hash unchanged, full content if changed
- `reset_cursor=true` resets tracking and returns full content
- Console logs do NOT use diff (always return full logs)

## Development Commands

### Setup
```bash
# Install in editable mode with dev dependencies
uv pip install -e ".[dev]"

# Or install globally
uv tool install .
```

### Running
```bash
# Start HTTP server (port 34501)
uv run playwright-proxy-server

# Start MCP client (stdio, for testing)
uv run playwright-proxy-client

# Or use globally installed commands
playwright-proxy-server
playwright-proxy-client
```

### Testing
```bash
# Run all tests (14 tests: 6 database + 8 diff)
uv run pytest

# Run specific test file
uv run pytest tests/test_database.py
uv run pytest tests/test_diff.py

# Run with coverage
uv run pytest --cov=playwright_mcp_proxy

# Run specific test
uv run pytest tests/test_database.py::test_create_and_get_session
```

### Code Quality
```bash
# Check formatting (Ruff)
uv run ruff check .

# Auto-fix
uv run ruff check --fix .
```

### Manual Testing
```bash
# Terminal 1: Start server
uv run playwright-proxy-server

# Terminal 2: Test HTTP endpoints
python examples/test_server.py      # Phase 1 features
python examples/test_diff.py        # Phase 2 diff functionality

# Terminal 3: Test MCP protocol
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | uv run playwright-proxy-client
```

## Code Structure

### Database Layer (database/)
- `schema.py` - SQLite DDL with tables: sessions, requests, responses, console_logs, diff_cursors
- `operations.py` - Async CRUD operations using aiosqlite
  - Session ops: create_session, get_session, update_session_activity, update_session_state
  - Request/Response ops: create_request, create_response, get_request, get_response
  - Console log ops: create_console_logs_batch, get_console_logs, get_console_error_count
  - Diff cursor ops (Phase 2): get_diff_cursor, upsert_diff_cursor, delete_diff_cursor

### HTTP Server (server/)
- `app.py` - FastAPI app with endpoints:
  - `POST /sessions` - Create new browser session
  - `POST /proxy` - Proxy request to Playwright, persist response, return metadata+ref_id
  - `GET /content/{ref_id}?search_for=&reset_cursor=` - Retrieve page snapshot (with diff)
  - `GET /console/{ref_id}?level=` - Retrieve console logs (no diff)
  - `GET /health` - Server health check
- `playwright_manager.py` - Subprocess lifecycle manager
  - Spawns/monitors/restarts Playwright subprocess
  - Health check loop with exponential backoff retry
  - JSON-RPC communication over stdio pipes

### MCP Client (client/)
- `mcp_server.py` - stdio MCP server using mcp.server.Server
  - Defines 9 tools (3 new + 6 proxied Playwright tools)
  - New tools: create_new_session, get_content, get_console_content
  - Proxied tools: browser_navigate, browser_snapshot, browser_click, browser_type, etc.
  - All proxied tools return metadata only, suggest using get_content for full data

### Models (models/)
- `api.py` - Pydantic models for HTTP API (ProxyRequest, ProxyResponse, ResponseMetadata)
- `database.py` - Pydantic models for DB records (Session, Request, Response, ConsoleLog, DiffCursor)

### Configuration (config.py)
- Pydantic Settings with env var support (prefix: `PLAYWRIGHT_PROXY_`)
- Settings: server (host, port), database (path), playwright (browser, headless), subprocess (health check intervals, restart policy)
- Load from .env file or environment variables

## Key Design Decisions

### Response Policy (Phase 1)
MCP responses return **metadata + ref_id only**, not full payloads:
```python
ProxyResponse(
    ref_id="uuid",
    status="success",
    metadata=ResponseMetadata(
        tool="browser_snapshot",
        has_snapshot=True,
        has_console_logs=True,
        console_error_count=2
    )
)
```
Clients use `get_content(ref_id)` to retrieve actual content from SQLite.

### Diff Algorithm (Phase 2)
Simple hash comparison (not line-by-line diff):
- Compute SHA256 of page_snapshot content
- Compare with `diff_cursors.last_snapshot_hash`
- If match: return empty string
- If differ: return full new content, update cursor
- Future enhancement: line-based diff for granular changes

### Session Lifecycle
- Sessions created via `create_new_session()` tool
- State: 'active' | 'closed' | 'error'
- On server crash: sessions marked 'closed' in DB, but data persists
- Phase 3 (future): session rehydration with browser state restoration

## Testing Strategy

- **Database tests** (test_database.py): CRUD operations, session management
- **Diff tests** (test_diff.py): Cursor ops, hash computation, first read/no changes/changed workflows, persistence
- **Manual tests** (examples/): HTTP endpoint testing with real Playwright subprocess
- All tests use temporary SQLite DBs (pytest fixtures with cleanup)

## Configuration

Environment variables (prefix `PLAYWRIGHT_PROXY_`):
```bash
# Server
PLAYWRIGHT_PROXY_SERVER_HOST=localhost
PLAYWRIGHT_PROXY_SERVER_PORT=34501

# Database
PLAYWRIGHT_PROXY_DATABASE_PATH=./proxy.db

# Playwright
PLAYWRIGHT_PROXY_PLAYWRIGHT_BROWSER=chrome  # chrome, firefox, webkit
PLAYWRIGHT_PROXY_PLAYWRIGHT_HEADLESS=false

# Subprocess Management
PLAYWRIGHT_PROXY_HEALTH_CHECK_INTERVAL=30  # seconds
PLAYWRIGHT_PROXY_MAX_RESTART_ATTEMPTS=3
PLAYWRIGHT_PROXY_RESTART_WINDOW=300  # 5 minutes
PLAYWRIGHT_PROXY_SHUTDOWN_TIMEOUT=5  # seconds

# Logging
PLAYWRIGHT_PROXY_LOG_LEVEL=INFO
```

Or create `.env` file (see `.env.example`).

## Common Patterns

### Adding a New Database Operation
1. Add method to `database/operations.py` (async, use `self.conn`)
2. Add model to `models/database.py` if needed (Pydantic BaseModel)
3. Write test in `tests/test_database.py` using `db` fixture

### Adding a New HTTP Endpoint
1. Add route to `server/app.py` (use FastAPI decorators)
2. Use `database` global for DB access, `playwright_manager` for subprocess
3. Return Pydantic models from `models/api.py`
4. Add manual test to `examples/`

### Adding a New MCP Tool
1. Define `Tool` in `client/mcp_server.py` TOOLS list (name, description, inputSchema)
2. Add handler logic in `handle_tool_call()` function
3. For proxied tools: forward to HTTP server via `/proxy` endpoint
4. For custom tools: implement directly with HTTP calls

## Troubleshooting

**Subprocess fails to start:**
- Ensure Node.js installed and `npx` available
- Run `npx @playwright/mcp@latest` manually to install
- Check stderr logs in server output

**Tests failing:**
- Ensure dev dependencies installed: `uv pip install -e ".[dev]"`
- Check for leftover SQLite files: `rm -f *.db*`
- Run with `-v` for verbose output: `uv run pytest -v`

**Port 34501 in use:**
- Set `PLAYWRIGHT_PROXY_SERVER_PORT=8080` or kill existing process: `lsof -i :34501`

**Import errors:**
- Reinstall in editable mode: `uv pip install -e .`
- For global install: `uv tool install --force .`

## Phase Roadmap

- **Phase 1** (Complete): Core infrastructure, SQLite persistence, HTTP server, MCP client, subprocess management
- **Phase 2** (Complete): Diff-based content retrieval with hash comparison, cursor persistence
- **Phase 3** (Future): Session state persistence, restart recovery, session_resume(session_id) tool
