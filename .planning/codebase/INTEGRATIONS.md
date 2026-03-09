# External Integrations

**Analysis Date:** 2026-03-09

## APIs & External Services

**Playwright MCP (subprocess):**
- The primary external integration is `@playwright/mcp@latest`, spawned as a child process
- Communication: JSON-RPC 2.0 over stdio pipes (stdin/stdout)
- Manager: `playwright_mcp_proxy/server/playwright_manager.py`
- Protocol version: `2024-11-05`
- Tools exposed by Playwright MCP: browser_navigate, browser_snapshot, browser_click, browser_type, browser_console_messages, browser_close, browser_evaluate
- No API key required; runs locally via `npx`

**No other external APIs are used.** This project is entirely self-contained and communicates only with a local Playwright subprocess.

## Data Storage

**Databases:**
- SQLite (file-based)
  - Connection: Configured via `PLAYWRIGHT_PROXY_DATABASE_PATH` env var (default: `./proxy.db`)
  - Client: `aiosqlite` (async wrapper around sqlite3)
  - Schema: `playwright_mcp_proxy/database/schema.py`
  - Operations: `playwright_mcp_proxy/database/operations.py`
  - Tables: `sessions`, `requests`, `responses`, `console_logs`, `diff_cursors`, `session_snapshots`
  - Initialization: Schema auto-created on startup via `CREATE TABLE IF NOT EXISTS`
  - No migrations system; schema changes are additive

**File Storage:**
- Local filesystem only (SQLite database file)
- No cloud storage or object storage

**Caching:**
- None. All data served directly from SQLite.
- Diff cursors (`diff_cursors` table) provide a form of read-state tracking but not caching.

## Authentication & Identity

**Auth Provider:**
- None. No authentication on any endpoint.
- The HTTP server (`localhost:34501`) is designed for local use only.
- MCP client communicates via stdio (inherently local).

## Monitoring & Observability

**Error Tracking:**
- None (no Sentry, Datadog, etc.)

**Logs:**
- Python `logging` module with configurable level via `PLAYWRIGHT_PROXY_LOG_LEVEL`
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
- Configured in `playwright_mcp_proxy/server/app.py` (line 24)
- Subprocess stderr monitored and logged at DEBUG level (`playwright_manager.py` line 282-294)

**Health Checks:**
- `GET /health` endpoint in `playwright_mcp_proxy/server/app.py`
- Returns subprocess health status: `{"status": "healthy"|"degraded", "playwright_subprocess": "running"|"down"}`
- Internal health check loop: sends `tools/list` ping every 30s to subprocess
- 3-strike failure detection before marking unhealthy

## CI/CD & Deployment

**Hosting:**
- Local execution only. No cloud deployment configuration detected.
- No Dockerfile, docker-compose, or cloud deployment manifests present.

**CI Pipeline:**
- None detected. No GitHub Actions, CircleCI, or other CI config files present.

## Environment Configuration

**Required env vars:**
- None strictly required; all have defaults in `playwright_mcp_proxy/config.py`

**Commonly configured env vars (prefix `PLAYWRIGHT_PROXY_`):**
- `SERVER_HOST` - HTTP server bind address (default: localhost)
- `SERVER_PORT` - HTTP server port (default: 34501)
- `DATABASE_PATH` - SQLite file path (default: ./proxy.db)
- `PLAYWRIGHT_BROWSER` - Browser choice: chrome, firefox, webkit (default: None/system default)
- `PLAYWRIGHT_HEADLESS` - Headless mode (default: false)
- `LOG_LEVEL` - Logging level (default: INFO)
- `HEALTH_CHECK_INTERVAL` - Subprocess health ping interval (default: 30)
- `MAX_RESTART_ATTEMPTS` - Max subprocess restarts per window (default: 3)
- `SESSION_SNAPSHOT_INTERVAL` - State capture interval (default: 30)
- `MAX_SESSION_AGE` - Max recoverable session age (default: 86400)
- `AUTO_REHYDRATE` - Auto-restore sessions on startup (default: false)

**Secrets location:**
- `.env` file (gitignored) for local development
- `.env.example` provided as template
- No secrets required; no API keys or tokens needed

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Internal Communication

**MCP Client -> HTTP Server:**
- Protocol: HTTP/JSON over localhost
- Client: `httpx.AsyncClient` with 30s timeout (`playwright_mcp_proxy/client/mcp_server.py` line 271)
- Endpoints used:
  - `POST /sessions` - Create session
  - `POST /proxy` - Forward tool calls
  - `GET /content/{ref_id}` - Retrieve page snapshots
  - `GET /console/{ref_id}` - Retrieve console logs

**HTTP Server -> Playwright Subprocess:**
- Protocol: JSON-RPC 2.0 over stdio pipes
- Manager: `playwright_mcp_proxy/server/playwright_manager.py`
- Async lock ensures serialized access to subprocess pipes
- Custom chunked line reader handles responses exceeding 64KB buffer limit

**Upstream Client -> MCP Client:**
- Protocol: MCP over stdio (e.g., Claude Desktop connects to this)
- Server: `mcp.server.Server` with `stdio_server()` transport
- 9 tools exposed (3 custom + 6 proxied Playwright tools)

---

*Integration audit: 2026-03-09*
