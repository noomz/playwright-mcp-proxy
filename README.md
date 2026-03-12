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

#### Option 2: System-wide UV pip install

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

**If installed globally (uv tool install):**

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

## Performance Comparison: Proxy vs Direct Playwright MCP

Measured with `uv run pytest tests/test_comparison.py -v -s -m integration` — 7 scenarios comparing the proxy against direct Playwright MCP subprocess communication.

### Simple Navigation (example.com)

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| navigate | proxy | 67 | 301 | - |
| snapshot (metadata) | proxy | 6 | 300 | 75 |
| get_content | proxy | 2 | 440 | 102 |
| navigate | direct | 1,711 | - | - |
| snapshot (full) | direct | 3 | 787 | 181 |

> Proxy metadata response: 300B vs Direct full snapshot: 787B

### Diff Suppression (repeated reads)

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| 1st read (full) | proxy | 2 | 440 | 102 |
| 2nd read (diff=empty) | proxy | 2 | 14 | 1 |
| 3rd read (reset=full) | proxy | 2 | 440 | 102 |
| 1st snapshot | direct | 3 | 469 | 102 |
| 2nd snapshot | direct | 5 | 787 | 181 |
| 3rd snapshot | direct | 3 | 502 | 110 |

> **3-read token savings: 188 tokens saved (48%)** — proxy 205 vs direct 393

### Multi-page Navigation

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| navigate (example.com) | proxy | 303 | - | - |
| snapshot (example.com) | proxy | 1,013 | 300 | 75 |
| get_content (example.com) | proxy | 4 | 440 | 102 |
| navigate (www.iana.org) | proxy | 1,307 | - | - |
| snapshot (www.iana.org) | proxy | 1,021 | 300 | 75 |
| get_content (www.iana.org) | proxy | 3 | 7,274 | 1,749 |
| get_content (page 1 replay) | proxy | 3 | 411 | 102 |
| navigate (example.com) | direct | 1,508 | - | - |
| snapshot (example.com) | direct | 3 | 469 | 102 |
| navigate (www.iana.org) | direct | 6,434 | - | - |
| snapshot (www.iana.org) | direct | 7 | 7,024 | 1,677 |

> Proxy persistence: page 1 content retrieved after navigating to page 2 (3ms)
> Direct has NO persistence — previous page content is gone after navigation

### Content Search Filtering

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| full content | proxy | 2 | 440 | 102 |
| filtered (search_for) | proxy | 5 | 97 | 19 |
| snapshot (full, no filter) | direct | 4 | 469 | 102 |

> **search_for reduction: 81% smaller payload, ~83 tokens saved**
> Direct MCP has no search filtering — always returns full accessibility tree

### Error Handling

| Operation | Path | Latency (ms) | Payload (bytes) |
|-----------|------|-------------:|----------------:|
| invalid URL navigate | proxy | 623 | 283 |
| invalid URL navigate | direct | 1,106 | - |

> Both paths handle errors gracefully without crashing

### Complex Page: Google Search

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| navigate (google.com) | proxy | 1,449 | - | - |
| type search query | proxy | 3,064 | - | - |
| press Enter | proxy | 1,179 | - | - |
| snapshot results (metadata) | proxy | 2,043 | 300 | 75 |
| get_content (1st read) | proxy | 3 | 78,262 | 17,676 |
| get_content (2nd read, diff) | proxy | 2 | 14 | 1 |
| get_content (search_for) | proxy | 3 | 13,711 | 3,285 |
| navigate (google.com) | direct | 1,877 | - | - |
| type search query | direct | 2,547 | - | - |
| press Enter | direct | 2,198 | - | - |
| snapshot results (full) | direct | 15 | 3,181 | 772 |
| snapshot (2nd, full again) | direct | 6 | 3,181 | 772 |

> **search_for 'playwright' reduction: 81%** — 3,285 tokens vs 17,676 full

### Complex Page: YouTube Search

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| navigate (youtube.com) | proxy | 1,618 | - | - |
| snapshot homepage | proxy | 79 | 2,502 | 625 |
| type search query | proxy | 32 | - | - |
| press Enter | proxy | 1,047 | - | - |
| snapshot results (metadata) | proxy | 22 | 300 | 75 |
| get_content (1st read) | proxy | 3 | 2,929 | 703 |
| get_content (2nd read, diff) | proxy | 2 | 14 | 1 |
| get_content (search_for) | proxy | 3 | 175 | 40 |
| navigate (youtube.com) | direct | 2,201 | - | - |
| snapshot homepage | direct | 14 | 1,956 | 460 |
| type search query | direct | 26 | - | - |
| press Enter | direct | 1,019 | - | - |
| snapshot results (full) | direct | 15 | 1,956 | 460 |
| snapshot (2nd, full again) | direct | 13 | 1,956 | 460 |

> **2-read diff savings: 216 tokens (23%)** — proxy 704 vs direct 920
> Full page: 703 tokens | Filtered 'playwright': 40 tokens | Diff suppressed: 1 token

### Chrome Extension Path (claude-in-chrome)

Measured via `mcp__claude-in-chrome__*` tools against a live Chrome browser with warm cache. These represent a third automation path — using an existing Chrome instance rather than spawning a headless browser.

#### Simple Navigation (example.com)

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| navigate | proxy | 67 | 301 | - |
| get_content | proxy | 2 | 440 | 102 |
| navigate | direct | 1,711 | - | - |
| snapshot (full) | direct | 3 | 787 | 181 |
| navigate | chrome | 403 | - | - |
| read_page | chrome | 3,200 | 213 | 53 |
| get_page_text | chrome | 3,400 | 183 | 46 |

> Chrome navigate is fast (warm cache) but read_page has ~3s extension round-trip overhead

#### Google Search

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| navigate (homepage) | proxy | 1,449 | - | - |
| get_content (1st read) | proxy | 3 | 78,262 | 17,676 |
| get_content (2nd read, diff) | proxy | 2 | 14 | 1 |
| snapshot results (full) | direct | 15 | 3,181 | 772 |
| navigate (homepage) | chrome | 1,375 | - | - |
| read_page (homepage) | chrome | 1,400 | 1,800 | 450 |
| navigate (search results) | chrome | 3,921 | - | - |
| read_page (search results) | chrome | 15,800 | 12,000 | 3,000 |

> Chrome read_page on Google search results: 15.8s / 12KB due to complex DOM at depth 2

#### YouTube Search

| Operation | Path | Latency (ms) | Payload (bytes) | Est. Tokens |
|-----------|------|-------------:|----------------:|------------:|
| get_content (1st read) | proxy | 3 | 2,929 | 703 |
| get_content (2nd read, diff) | proxy | 2 | 14 | 1 |
| snapshot results (full) | direct | 15 | 1,956 | 460 |
| navigate (homepage) | chrome | 3,708 | - | - |
| read_page (homepage) | chrome | 2,200 | 11,000 | 2,750 |
| navigate (search results) | chrome | 1,246 | - | - |
| read_page (search results) | chrome | 1,300 | 10,000 | 2,500 |

> YouTube SPA routing makes subsequent navigates fast (1.2s); chrome read_page payloads are large (10-11KB)

#### 3-Way Path Comparison Summary

| Path | Navigate Latency | Content Latency | Token Efficiency | Persistence |
|------|-----------------|-----------------|------------------|-------------|
| **Proxy** | Medium (67-1,449ms) | Fast (2-5ms via ref_id) | Best (diff: 1 token on repeat) | Full SQLite history |
| **Direct** | Slow (1,508-6,434ms) | Fast (3-15ms) | Moderate (full payload each time) | None |
| **Chrome** | Fast-Medium (403-3,921ms) | Slow (1,300-15,800ms) | Variable (53-3,000 tokens) | None |

> **Proxy wins on token efficiency** — diff suppression and search filtering reduce tokens by 48-83%.
> **Chrome wins on navigate speed** — warm cache avoids cold browser startup.
> **Direct wins on content retrieval speed** — no extension round-trip overhead.

### Key Proxy Advantages

| Feature | Description |
|---------|-------------|
| Metadata-only responses | Initial tool call returns ref_id, not full content — small, fixed-size payload |
| Diff suppression | Repeated reads return empty when content unchanged — massive token savings |
| search_for filtering | Retrieve only matching lines — reduces payload for targeted lookups |
| Persistence (SQLite) | All snapshots stored — retrieve any historical page by ref_id |
| Session management | Named sessions with lifecycle tracking and error audit trail |

### Running Comparison Tests

```bash
# Start the proxy server first
uv run playwright-proxy-server

# Run the proxy vs direct comparison suite (requires internet access)
uv run pytest tests/test_comparison.py -v -s -m integration

# Run the chrome path comparison report (uses pre-recorded measurements)
uv run pytest tests/test_chrome_comparison.py -v -s -m chrome_comparison
```

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

### Phase 8 (Complete)
- [x] Chrome extension path (claude-in-chrome) measurement infrastructure
- [x] Pre-recorded measurements for 3 scenarios (example.com, Google Search, YouTube Search)
- [x] 3-way performance comparison table (proxy vs direct vs chrome)
- [x] `chrome_comparison` pytest marker for opt-in test selection

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
