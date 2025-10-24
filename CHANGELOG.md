# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3] - 2025-10-24

### Fixed

- **Critical: asyncio buffer limit errors** (`asyncio.LimitOverrunError`)
  - Implemented chunked reading in `playwright_manager.py` to handle responses >64KB
  - Added `_read_line_chunked()` method that catches `LimitOverrunError` and reads in chunks
  - Fixes "Separator is found, but chunk exceed the limit" errors when Playwright returns large page snapshots
  - Solution based on https://github.com/ipython/ipython/issues/14005
  - Now supports unlimited response sizes (no 64KB buffer limit)

### Added

- **Comprehensive error tracebacks**
  - Added `traceback.format_exc()` to all error logging
  - Helps diagnose production issues with full stack traces
  - Applied to both HTTP server and subprocess manager

- **TROUBLESHOOTING.md documentation**
  - Common issues and solutions
  - Debugging tips and health check commands
  - Version-specific notes

- **Test scripts**
  - `examples/debug_playwright_response.py` - Debug response sizes
  - `examples/test_click_error.py` - Test browser_click scenarios
  - `examples/test_user_scenario.py` - Test specific user scenarios

### Testing

- Verified chunked reading handles responses >64KB
- Confirmed `get_content()` still returns full page snapshots
- All existing functionality preserved
- No data loss (full content still accessible)

## [0.2.2] - 2025-10-24

### Fixed

- **MCP client response sizes**
  - Shortened success messages to single compact line
  - Format: `✓ tool_name | ref_id | snapshot: get_content('ref_id')`
  - Truncate all error messages to 200 chars max
  - Prevents MCP protocol buffer overflow when sending responses back to upstream client

### Impact

- Reduced MCP client response messages from ~10 lines to 1 line
- Helps avoid buffer limits in MCP protocol layer
- Full content still accessible via `get_content()` and `get_console_content()`

## [0.2.1] - 2025-10-22

### Fixed

- **MCP message size limit error** (`Separator is found, but chunk is longer than limit`)
  - Changed response storage to only persist minimal metadata instead of full Playwright payloads
  - Now stores only `tool` name and `isError` flag in `responses.result` field
  - Full page snapshots and console logs already stored in dedicated fields
  - Response sizes reduced from potentially 10KB+ to ~300 bytes
  - Full content still accessible via `/content/{ref_id}` and `/console/{ref_id}` endpoints

- **Error message truncation**
  - Added `truncate_error()` helper function
  - Error messages truncated to 500 characters in MCP responses
  - Full error messages still stored in database for debugging
  - Prevents MCP protocol size limit violations on error responses

### Testing

- Added `examples/test_bug_fix.py` to verify fix
- Verified browser_navigate no longer causes size limit errors
- Confirmed response sizes are reasonable (<2KB)
- Validated full content retrieval via dedicated endpoints

## [0.2.0] - 2025-10-22

### Added

#### Phase 2: Diff-Based Content Retrieval

- **Hash-based change detection** for `get_content` endpoint
  - Content changes tracked using SHA256 hashes
  - Returns only changed content on subsequent reads
  - Empty response when no changes detected

- **Diff cursor persistence**
  - `diff_cursors` table in SQLite for tracking read state
  - Cursors persist across server restarts
  - Database operations: `get_diff_cursor`, `upsert_diff_cursor`, `delete_diff_cursor`

- **reset_cursor parameter**
  - `get_content(ref_id, reset_cursor=true)` resets diff tracking
  - Returns full content and creates new cursor baseline
  - Useful for forcing full content retrieval

- **MCP client enhancements**
  - Updated `get_content` tool with `reset_cursor` parameter
  - Helpful message when content unchanged: "(No changes since last read...)"
  - Boolean parameter in tool schema

#### Testing

- 8 new diff-related tests (total: 14 tests, all passing)
  - Diff cursor CRUD operations
  - Hash computation consistency
  - First read workflow (full content + cursor creation)
  - No changes workflow (empty response)
  - Content changed workflow (full new content)
  - Cursor persistence across database restart
  - Reset cursor functionality

#### Documentation

- Updated README with Phase 2 features
- Documented diff behavior in Available Tools section
- Updated Roadmap marking Phase 2 as complete

### Technical Details

**Diff Algorithm:**
- Simple hash comparison (SHA256)
- If hash matches: return empty string
- If hash differs: return full new content
- Cursor stores: ref_id, cursor_position, last_snapshot_hash, last_read

**Acceptance Criteria Met:**
- ✅ get_content(ref_id) returns only content changed since last call
- ✅ get_content(ref_id, reset_cursor=True) resets diff and returns full content
- ✅ Cursor persists across server restarts (SQLite-backed)
- ✅ Empty diff returns empty string (not error)
- ✅ Initial read (no cursor) returns full content
- ✅ Diff algorithm: simple string comparison (hash-based)
- ✅ Console logs do NOT implement diff (always return full logs)

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

[0.2.3]: https://github.com/yourusername/playwright-mcp-proxy/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/yourusername/playwright-mcp-proxy/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/yourusername/playwright-mcp-proxy/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/yourusername/playwright-mcp-proxy/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/yourusername/playwright-mcp-proxy/releases/tag/v0.1.0
