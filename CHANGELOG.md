# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2025-10-22

### Added

#### Core Infrastructure
- UV-based Python project structure with pyproject.toml
- Configuration system using Pydantic Settings
- Environment variable support with `PLAYWRIGHT_PROXY_` prefix
- SQLite database with full schema (sessions, requests, responses, console_logs, diff_cursors)
- Database operations layer with async SQLite support

#### HTTP Server Component
- FastAPI server on port 34501
- `/health` endpoint for health checks
- `/sessions` endpoint for creating new browser sessions
- `/proxy` endpoint for proxying Playwright MCP requests
- `/content/{ref_id}` endpoint for retrieving page snapshots
- `/console/{ref_id}` endpoint for retrieving console logs
- Playwright MCP subprocess lifecycle management:
  - Automatic spawning and initialization
  - Health monitoring with configurable intervals
  - Auto-restart with exponential backoff (max 3 attempts)
  - Graceful shutdown handling
  - stderr monitoring and logging

#### MCP Client Component
- stdio MCP server using MCP SDK
- HTTP client for communicating with proxy server
- Tool definitions for:
  - `create_new_session()` - Create browser sessions
  - `get_content(ref_id, search_for)` - Retrieve page snapshots
  - `get_console_content(ref_id, level)` - Retrieve console logs
  - All Playwright tools (proxied): browser_navigate, browser_snapshot, browser_click, browser_type, etc.
- Phase 1 response policy: Returns metadata + ref_id instead of full payloads
- Console logs suppressed by default in responses

#### Data Persistence
- UUID-based reference IDs for all requests
- Full request/response storage as JSON blobs
- Page snapshot persistence (exact text format)
- Console log normalization with level filtering
- Session state tracking (active, closed, error)
- Timestamp tracking for all entities

#### Documentation
- Comprehensive README with installation, configuration, and usage
- .env.example with all configuration options
- .current-work.md with design decisions and implementation notes
- Inline code documentation and type hints

#### Testing
- pytest configuration with asyncio support
- Database layer unit tests (6 tests, all passing)
- Test fixtures for temporary database instances
- Example script for testing HTTP server directly

#### Developer Experience
- Ruff configuration for code formatting
- Entry point scripts: `playwright-proxy-server` and `playwright-proxy-client`
- .gitignore for Python, database, and IDE files
- Clear separation of concerns (client, server, database, models)

### Future Phases

#### Phase 2 (Contracted)
- Diff-based content retrieval
- `get_content` returns only changes since last read
- Cursor reset functionality
- Hash-based change detection

#### Phase 3 (Important but Not Urgent)
- Session state persistence and rehydration
- Restart recovery with browser state restoration
- `session_resume(session_id)` tool
- Reconnection handling for MCP client

### Technical Details

**Storage Format:**
- `responses.result`: JSON string blob (unparsed, exact bytes)
- `responses.page_snapshot`: TEXT blob (preserving exact formatting)
- `responses.console_logs`: JSON string (backup/redundancy)
- No transformation on write, enabling future diff implementation

**Subprocess Management:**
- Health check interval: 30s (configurable)
- Max restart attempts: 3 per 5-minute window
- Restart backoff: 1s, 2s, 4s
- Graceful shutdown timeout: 5s
- SIGKILL as fallback

**Dependencies:**
- fastapi, uvicorn (HTTP server)
- aiosqlite (async SQLite)
- mcp (MCP SDK)
- httpx (HTTP client)
- pydantic, pydantic-settings (data validation & config)
- psutil (subprocess monitoring)
- pytest, pytest-asyncio (testing)
- ruff (formatting)

[0.1.0]: https://github.com/yourusername/playwright-mcp-proxy/releases/tag/v0.1.0
