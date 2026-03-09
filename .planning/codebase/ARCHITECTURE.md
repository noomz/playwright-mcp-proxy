# Architecture

**Analysis Date:** 2026-03-09

## Pattern Overview

**Overall:** Two-component proxy architecture (MCP Client + HTTP Server) wrapping a Playwright MCP subprocess, with SQLite persistence and session state management.

**Key Characteristics:**
- Two independent processes communicate over HTTP (client -> server)
- Server manages a single Playwright MCP subprocess via JSON-RPC over stdio pipes
- All Playwright responses persisted to SQLite as raw blobs before returning metadata-only responses
- Diff-based content retrieval using SHA256 hash comparison (Phase 2)
- Periodic session state snapshots with orphaned session recovery (Phase 7)

## Layers

**MCP Client Layer (stdio interface):**
- Purpose: Expose browser automation tools to upstream MCP clients (e.g., Claude Desktop)
- Location: `playwright_mcp_proxy/client/mcp_server.py`
- Contains: Tool definitions (9 tools), tool call handler, MCP protocol server
- Depends on: HTTP Server (via httpx), `mcp` SDK, `playwright_mcp_proxy.config`
- Used by: External MCP clients via stdio protocol

**HTTP Server Layer (FastAPI):**
- Purpose: Receive proxied requests, manage Playwright subprocess, persist data, serve content
- Location: `playwright_mcp_proxy/server/app.py`
- Contains: FastAPI app factory, endpoint handlers, lifespan management, diff logic
- Depends on: Database layer, PlaywrightManager, SessionStateManager, models
- Used by: MCP Client layer via HTTP

**Subprocess Management Layer:**
- Purpose: Spawn, monitor, and restart the Playwright MCP subprocess
- Location: `playwright_mcp_proxy/server/playwright_manager.py`
- Contains: Process lifecycle, JSON-RPC communication, health checks, auto-restart
- Depends on: `playwright_mcp_proxy.config` for settings
- Used by: HTTP Server layer, SessionStateManager

**Session State Layer:**
- Purpose: Capture and restore browser state for session recovery across restarts
- Location: `playwright_mcp_proxy/server/session_state.py`
- Contains: State capture via `browser_evaluate`, state restoration, cookie parsing
- Depends on: PlaywrightManager (for browser communication), database models
- Used by: HTTP Server (periodic snapshot task, resume endpoint)

**Database Layer:**
- Purpose: Async SQLite persistence for sessions, requests, responses, snapshots
- Location: `playwright_mcp_proxy/database/`
- Contains: Schema DDL (`schema.py`), async CRUD operations (`operations.py`)
- Depends on: aiosqlite, Pydantic models from `models/database.py`
- Used by: HTTP Server layer

**Models Layer:**
- Purpose: Define data shapes for API and database records
- Location: `playwright_mcp_proxy/models/`
- Contains: API models (`api.py`), database models (`database.py`)
- Depends on: Pydantic
- Used by: All other layers

**Configuration Layer:**
- Purpose: Centralized settings with env var support
- Location: `playwright_mcp_proxy/config.py`
- Contains: Pydantic Settings class, global `settings` singleton
- Depends on: pydantic-settings, python-dotenv
- Used by: All other layers

## Data Flow

**Tool Call Flow (main path):**

1. External MCP client sends JSON-RPC `tools/call` over stdio to MCP Client
2. MCP Client (`handle_tool_call()` in `client/mcp_server.py`) receives tool name + arguments
3. For proxied tools: MCP Client sends HTTP POST to `http://localhost:34501/proxy` with `ProxyRequest`
4. HTTP Server verifies session is active, creates `Request` record in SQLite
5. HTTP Server forwards as JSON-RPC to Playwright subprocess via `PlaywrightManager.send_request()`
6. Playwright subprocess executes browser action, returns JSON-RPC response via stdout
7. HTTP Server extracts page_snapshot/console_logs, creates `Response` record in SQLite
8. HTTP Server returns `ProxyResponse` (metadata + ref_id only, no content) to MCP Client
9. MCP Client formats minimal text response: `"browser_snapshot | <ref_id> | snapshot: get_content('<ref_id>')"`
10. External client later calls `get_content(ref_id)` to retrieve actual content from SQLite

**Content Retrieval Flow (diff-based):**

1. MCP Client calls `GET /content/{ref_id}` on HTTP Server
2. Server loads `Response.page_snapshot` from SQLite
3. If `search_for` param: filter lines with optional before/after context (grep-like)
4. Check `diff_cursors` table for existing cursor:
   - No cursor (first read): return full content, create cursor with SHA256 hash
   - Cursor exists, hash matches: return empty string (no changes)
   - Cursor exists, hash differs: return full new content, update cursor hash
5. MCP Client returns content or "(No changes since last read)" message

**Session Snapshot Flow (background):**

1. `periodic_snapshot_task()` runs every `session_snapshot_interval` seconds (default 30s)
2. Lists all active sessions from database
3. For each session: `SessionStateManager.capture_state()` calls `browser_evaluate` 5 times to get URL, cookies, localStorage, sessionStorage, viewport
4. Saves `SessionSnapshot` to `session_snapshots` table
5. Updates session record with inline state fields
6. Cleans up old snapshots (keeps last N per `max_session_snapshots`)

**State Management:**
- Session state: SQLite `sessions` table with states: `active`, `closed`, `error`, `recoverable`, `stale`, `failed`
- MCP Client holds `current_session_id` as module-level global (single session at a time)
- HTTP Server holds globals: `playwright_manager`, `database`, `session_state_manager`, `snapshot_task`
- Subprocess communication serialized via `asyncio.Lock` in `PlaywrightManager._lock`

## Key Abstractions

**PlaywrightManager:**
- Purpose: Encapsulates Playwright MCP subprocess lifecycle
- Location: `playwright_mcp_proxy/server/playwright_manager.py`
- Pattern: Process wrapper with health monitoring and auto-restart
- Key methods: `start()`, `stop()`, `send_request(method, params)`, `_attempt_restart()`
- Handles chunked reading for responses exceeding 64KB buffer limit

**Database:**
- Purpose: Async wrapper around aiosqlite with typed CRUD operations
- Location: `playwright_mcp_proxy/database/operations.py`
- Pattern: Repository pattern with Pydantic model mapping
- Key methods: `create_session()`, `create_request()`, `create_response()`, `get_response()`, `upsert_diff_cursor()`, `save_session_snapshot()`

**SessionStateManager:**
- Purpose: Captures and restores browser state via Playwright's `browser_evaluate` tool
- Location: `playwright_mcp_proxy/server/session_state.py`
- Pattern: State machine with capture/restore operations
- Key methods: `capture_state(session_id)`, `restore_state(snapshot)`

**ProxyResponse (metadata-only response):**
- Purpose: Return minimal metadata instead of full Playwright payloads
- Location: `playwright_mcp_proxy/models/api.py`
- Pattern: Reference-based content retrieval (ref_id points to stored data)
- Fields: `ref_id`, `session_id`, `status`, `metadata` (tool, has_snapshot, has_console_logs)

## Entry Points

**HTTP Server:**
- Location: `playwright_mcp_proxy/server/app.py` -> `main()`
- CLI command: `playwright-proxy-server` (defined in `pyproject.toml` `[project.scripts]`)
- Triggers: Direct CLI invocation
- Responsibilities: Start uvicorn with FastAPI app factory, initialize DB/Playwright/SessionState in lifespan

**MCP Client:**
- Location: `playwright_mcp_proxy/client/mcp_server.py` -> `main()`
- CLI command: `playwright-proxy-client` (defined in `pyproject.toml` `[project.scripts]`)
- Triggers: MCP host (e.g., Claude Desktop) spawns as subprocess
- Responsibilities: Run stdio MCP server, translate tool calls to HTTP requests

**Legacy main.py:**
- Location: `main.py` (project root)
- Purpose: Placeholder, prints "Hello from playwright-mcp-proxy!"
- Not used in actual operation

## Error Handling

**Strategy:** Try/except with logging at each layer, graceful degradation

**Patterns:**
- HTTP Server: Catches all exceptions in endpoint handlers, stores error in `Response` record, returns `ProxyResponse` with truncated error (max 500 chars) to prevent MCP buffer overflow
- PlaywrightManager: 3-strike health check failure triggers auto-restart with exponential backoff (1s, 2s, 4s); max 3 restarts per 5-minute window
- MCP Client: Catches `httpx.HTTPError` and generic `Exception`, truncates error messages to 200 chars
- Session state capture: Errors logged but do not stop the periodic snapshot task; individual session failures do not affect other sessions
- Subprocess shutdown: SIGTERM -> wait (5s timeout) -> SIGKILL fallback

## Cross-Cutting Concerns

**Logging:**
- Standard Python `logging` module throughout
- Level configurable via `PLAYWRIGHT_PROXY_LOG_LEVEL` env var (default: INFO)
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Each module uses `logging.getLogger(__name__)`

**Validation:**
- Pydantic models for all API request/response shapes (`models/api.py`)
- Pydantic models for all database records (`models/database.py`)
- SQLite CHECK constraints on `sessions.state` and `responses.status` and `console_logs.level`
- Session state validation in endpoints (must be "active" for proxy, "recoverable"/"stale" for resume)

**Authentication:**
- None. Server binds to localhost only. No auth on HTTP endpoints.

**Concurrency:**
- Single Playwright subprocess shared across all requests
- `asyncio.Lock` serializes JSON-RPC communication to subprocess
- All database operations use async/await via aiosqlite
- Background tasks: health check loop, stderr monitor, periodic snapshot task

---

*Architecture analysis: 2026-03-09*
