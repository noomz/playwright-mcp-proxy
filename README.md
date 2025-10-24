# Playwright MCP Proxy

A Model Context Protocol (MCP) proxy for Playwright that adds persistent storage, session management, and optimized response handling.

## Architecture

The proxy consists of two UV-based Python components:

1. **MCP Client** - A stdio MCP server that exposes Playwright tools to upstream clients
2. **HTTP Server** - Manages the Playwright MCP subprocess, handles sessions, and persists data to SQLite

```
MCP Client --> MCP Client --> HTTP Server --> Playwright MCP
(upstream)     (proxy)        (FastAPI)       (subprocess)
                                   |
                                   v
                                SQLite
```

## Features

- **Persistent Storage**: All requests and responses stored in SQLite with UUID references
- **Session Management**: UUID-based browser sessions that can be created and managed independently
- **Optimized Responses**: Returns metadata + ref_id instead of full payloads
- **Content Retrieval**: Get page snapshots and console logs by ref_id
- **Diff-Based Content** (Phase 2): `get_content` returns only changes since last read
  - Hash-based change detection
  - Cursor persistence across server restarts
  - `reset_cursor` parameter to get full content
- **Session Recovery** (Phase 7): Sessions survive server restarts
  - Automatic state snapshots every 30s (URL, cookies, localStorage, sessionStorage, viewport)
  - Orphaned session detection on startup
  - Resume sessions with full state restoration
  - Classification: recoverable, stale, or closed based on snapshot age
- **Subprocess Management**: Automatic health monitoring and restart for Playwright MCP

## Installation

### Local Development Install

```bash
# Install in editable mode with UV
uv pip install -e .

# Or install with dev dependencies
uv pip install -e ".[dev]"
```

### Global Install (Recommended for Production)

#### Option 1: UV Tool Install (Recommended)

Install as a global UV tool - commands will be available system-wide:

```bash
# Install from the current directory
uv tool install .

# Or install from a Git repository
uv tool install git+https://github.com/yourusername/playwright-mcp-proxy.git

# Commands are now available globally:
playwright-proxy-server
playwright-proxy-client
```

To update later:
```bash
uv tool upgrade playwright-mcp-proxy
```

To uninstall:
```bash
uv tool uninstall playwright-mcp-proxy
```

#### Option 2: pipx Install

If you prefer pipx:

```bash
# Install with pipx
pipx install .

# Or from Git
pipx install git+https://github.com/yourusername/playwright-mcp-proxy.git

# Commands available globally
playwright-proxy-server
playwright-proxy-client
```

#### Option 3: System-wide UV pip install

```bash
# Install to UV's global Python environment
uv pip install --system .
```

## Quick Start

### 1. Start the HTTP Server

```bash
# Using the installed script
playwright-proxy-server

# Or using Python module
python -m playwright_mcp_proxy.server
```

The server will:
- Initialize the SQLite database at `./proxy.db`
- Spawn the Playwright MCP subprocess
- Listen on `http://localhost:34501`

### 2. Configure MCP Client

Add to your MCP client configuration (e.g., Claude Desktop, VS Code):

**If installed globally (uv tool install or pipx):**

```json
{
  "mcpServers": {
    "playwright-proxy": {
      "command": "playwright-proxy-client"
    }
  }
}
```

**If using local development install:**

```json
{
  "mcpServers": {
    "playwright-proxy": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/playwright-mcp-proxy",
        "playwright-proxy-client"
      ]
    }
  }
}
```

**Or using the Python module directly:**

```json
{
  "mcpServers": {
    "playwright-proxy": {
      "command": "python",
      "args": [
        "-m",
        "playwright_mcp_proxy.client"
      ]
    }
  }
}
```

### 3. Use from MCP Client

```
# Create a new browser session
> create_new_session()
Created session: abc-123-def-456

# Navigate and take snapshot
> browser_navigate(url="https://example.com")
Request completed successfully
Ref ID: xyz-789
Page snapshot available. Use get_content('xyz-789')

# Get the page content
> get_content(ref_id="xyz-789")
[Full accessibility tree snapshot]

# Search within content
> get_content(ref_id="xyz-789", search_for="Example Domain")
- heading "Example Domain"
```

## Session Recovery (Phase 7)

Sessions now survive server restarts! The proxy automatically captures browser state every 30 seconds and can restore sessions after crashes or restarts.

### How It Works

1. **Automatic Snapshots**: While sessions are active, the server captures:
   - Current URL
   - Cookies
   - localStorage
   - sessionStorage
   - Viewport size

2. **Startup Detection**: When the server restarts, it automatically:
   - Detects orphaned sessions (marked as "active" before shutdown)
   - Classifies them based on snapshot age:
     - **recoverable**: Recent snapshot (< 24h) - safe to resume
     - **stale**: Old snapshot (> 24h) - may not work reliably
     - **closed**: No snapshot available - cannot recover

3. **Manual Resume**: Users can list and resume sessions via tools

### Usage Example

```
# Before restart - working in a session
> browser_navigate(url="https://example.com")
> browser_type(element="search box", ref="e1", text="test query")
# Server crashes or restarts...

# After restart - resume your session
> list_sessions(state="recoverable")
Session ID: abc-123-def-456
State: recoverable
URL: https://example.com
Snapshot age: 45 seconds

> resume_session(session_id="abc-123-def-456")
✓ Session resumed successfully
Restored URL: https://example.com
# Your browser is back at the same page with all state restored!
```

### HTTP API

You can also use the HTTP endpoints directly:

```bash
# List recoverable sessions
curl http://localhost:34501/sessions?state=recoverable

# Resume a session
curl -X POST http://localhost:34501/sessions/abc-123-def-456/resume
```

### Configuration

- `SESSION_SNAPSHOT_INTERVAL`: How often to snapshot (default: 30s)
- `MAX_SESSION_AGE`: Max age for recoverable sessions (default: 24h)
- `MAX_SESSION_SNAPSHOTS`: How many snapshots to keep (default: 10)
- `AUTO_REHYDRATE`: Auto-resume sessions on startup (default: false)

### Limitations

- Cookies captured via `document.cookie` (no httpOnly/secure flags)
- Cannot capture JavaScript heap, running timers, or pending requests
- Some sites may break if only storage is restored without full context
- Viewport size captured but not currently restored (Playwright limitation)

## Configuration

Configuration via environment variables (prefix: `PLAYWRIGHT_PROXY_`):

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
PLAYWRIGHT_PROXY_HEALTH_CHECK_INTERVAL=30
PLAYWRIGHT_PROXY_MAX_RESTART_ATTEMPTS=3
PLAYWRIGHT_PROXY_RESTART_WINDOW=300
PLAYWRIGHT_PROXY_SHUTDOWN_TIMEOUT=5

# Session Recovery (Phase 7)
PLAYWRIGHT_PROXY_SESSION_SNAPSHOT_INTERVAL=30    # Seconds between snapshots
PLAYWRIGHT_PROXY_MAX_SESSION_AGE=86400           # Max age (24h) for recoverable sessions
PLAYWRIGHT_PROXY_AUTO_REHYDRATE=false            # Auto-resume sessions on startup
PLAYWRIGHT_PROXY_MAX_SESSION_SNAPSHOTS=10        # Keep last N snapshots per session

# Logging
PLAYWRIGHT_PROXY_LOG_LEVEL=INFO
```

Or create a `.env` file (see `.env.example`).

## Available Tools

### Session Management

- `create_new_session()` - Create a new browser session, returns `session_id`
- `list_sessions(state?)` - List all sessions, optionally filtered by state (Phase 7)
- `resume_session(session_id)` - Resume a recoverable/stale session after restart (Phase 7)

### Content Retrieval

- `get_content(ref_id, search_for?, reset_cursor?)` - Get page snapshot from a previous request
  - **Phase 2**: Returns only changes since last read (hash-based diff)
  - Use `reset_cursor=true` to get full content and reset diff tracking
  - Empty response means no changes detected
- `get_console_content(ref_id, level?)` - Get console logs (filter by debug/info/warn/error)

### Playwright Tools (Proxied)

All standard Playwright MCP tools are available:

- `browser_navigate(url)`
- `browser_snapshot()`
- `browser_click(element, ref)`
- `browser_type(element, ref, text, submit?)`
- `browser_console_messages(onlyErrors?)`
- `browser_close()`
- ... and more

Responses return metadata + ref_id instead of full content.

## Database Schema

- **sessions** - Browser sessions (UUID, state, timestamps, recovery fields)
- **requests** - All proxied requests (ref_id, tool, params)
- **responses** - Full responses as blobs (result, page_snapshot, console_logs)
- **console_logs** - Normalized console entries (level, message, location)
- **diff_cursors** - For Phase 2 diff support
- **session_snapshots** - Phase 7 state snapshots (URL, cookies, storage, viewport)

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=playwright_mcp_proxy

# Run specific test file
uv run pytest tests/test_database.py
```

### Code Formatting

```bash
# Check formatting
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .
```

### Manual Testing

```bash
# Terminal 1: Start server
uv run playwright-proxy-server

# Terminal 2: Start client (stdio)
uv run playwright-proxy-client

# Terminal 3: Send MCP requests via stdio
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | uv run playwright-proxy-client
```

## Roadmap

### Phase 1 (Complete)
- [x] Core infrastructure
- [x] SQLite persistence
- [x] HTTP server with session management
- [x] MCP client with tool proxying
- [x] Subprocess lifecycle management
- [x] Basic testing (6 tests)

### Phase 2 (Complete)
- [x] Diff-based content retrieval
- [x] `get_content` returns only changes since last read
- [x] `reset_cursor` parameter
- [x] Hash-based change detection
- [x] Cursor persistence across server restarts
- [x] Comprehensive tests (8 additional tests)

### Phase 7 (Complete)
- [x] Session state persistence (URL, cookies, localStorage, sessionStorage, viewport)
- [x] Automatic periodic snapshots every 30s
- [x] Orphaned session detection on startup
- [x] Session classification (recoverable/stale/closed)
- [x] Restart recovery with session rehydration
- [x] `list_sessions(state)` tool
- [x] `resume_session(session_id)` tool
- [x] Comprehensive tests (16 tests total)

## Troubleshooting

### Server won't start

- Check if port 34501 is available
- Verify Node.js is installed (for Playwright MCP)
- Check logs in console output

### Subprocess keeps restarting

- Check `~/.npm` has `@playwright/mcp@latest` installed
- Verify browser binaries are installed
- Review stderr logs

### MCP client can't connect

- Ensure HTTP server is running on localhost:34501
- Check firewall settings
- Verify configuration in MCP client

## License

MIT

## Contributing

Contributions welcome! Please:
1. Follow the existing code style (Ruff)
2. Add tests for new features
3. Update documentation
4. Ensure backward compatibility

Areas for contribution:
- Integration tests for session recovery
- Performance optimizations
- Additional browser state capture (iframe support, web workers, etc.)
- Enhanced rehydration strategies
- Bug fixes and improvements

See `CLAUDE.md` for architecture details and development patterns.
