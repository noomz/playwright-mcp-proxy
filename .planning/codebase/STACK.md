# Technology Stack

**Analysis Date:** 2026-03-09

## Languages

**Primary:**
- Python 3.12+ (target: 3.14) - All application code

**Secondary:**
- SQL (SQLite dialect) - Database schema in `playwright_mcp_proxy/database/schema.py`
- JavaScript - Inline eval strings for browser state capture in `playwright_mcp_proxy/server/session_state.py`

## Runtime

**Environment:**
- Python 3.14 (pinned in `.python-version`)
- Requires Python >= 3.12 (declared in `pyproject.toml`)

**Package Manager:**
- uv (Astral) - Used for dependency management, running, and tool installation
- Lockfile: `uv.lock` present (revision 2)

**Build System:**
- Hatchling (`hatchling.build` backend in `pyproject.toml`)

## Frameworks

**Core:**
- FastAPI >= 0.115.0 - HTTP server (`playwright_mcp_proxy/server/app.py`)
- MCP SDK >= 1.0.0 - MCP stdio server protocol (`playwright_mcp_proxy/client/mcp_server.py`)
- Pydantic >= 2.9.0 - Data models (`playwright_mcp_proxy/models/`)
- pydantic-settings - Configuration management (`playwright_mcp_proxy/config.py`)

**Testing:**
- pytest >= 8.3.0 - Test runner
- pytest-asyncio >= 0.24.0 - Async test support (mode: `auto`)
- pytest-cov >= 6.0.0 - Coverage reporting

**Build/Dev:**
- Ruff >= 0.7.0 - Linting and formatting
- Hatchling - Build backend

## Key Dependencies

**Critical:**
- `fastapi` >= 0.115.0 - HTTP API framework for the proxy server
- `mcp` >= 1.0.0 - Model Context Protocol SDK for stdio server/client
- `aiosqlite` >= 0.20.0 - Async SQLite driver, sole database interface
- `httpx` >= 0.27.0 - Async HTTP client for MCP client to server communication
- `pydantic` >= 2.9.0 - Data validation and serialization for all models
- `uvicorn` >= 0.32.0 - ASGI server to run FastAPI

**Infrastructure:**
- `python-dotenv` >= 1.0.0 - Environment variable loading from `.env` files
- `psutil` >= 6.1.0 - Process utilities (available but not heavily used currently)

**External Subprocess:**
- `npx @playwright/mcp@latest` - Playwright MCP server spawned as a child process (requires Node.js)

## Configuration

**Environment:**
- Pydantic Settings with `PLAYWRIGHT_PROXY_` prefix (`playwright_mcp_proxy/config.py`)
- Loads from `.env` file or environment variables
- `.env.example` present for reference (`.env` itself is gitignored)
- Key settings: server host/port, database path, playwright browser/headless, health check intervals, session recovery options

**Critical Config Values:**
- `server_host`: localhost (default)
- `server_port`: 34501 (default)
- `database_path`: ./proxy.db (default)
- `playwright_command`: npx (default)
- `playwright_args`: ["@playwright/mcp@latest"] (default)
- `health_check_interval`: 30s
- `max_restart_attempts`: 3
- `restart_window`: 300s (5 min)
- `session_snapshot_interval`: 30s
- `max_session_age`: 86400s (24h)

**Build:**
- `pyproject.toml` - Single source of truth for project metadata, dependencies, tool config
- Ruff config: line-length 100, target py312, lint rules E/F/I/N/W (ignores E501)
- pytest config: asyncio_mode auto, testpaths ["tests"]

## Entry Points

**CLI Scripts (defined in `pyproject.toml [project.scripts]`):**
- `playwright-proxy-server` -> `playwright_mcp_proxy.server:main` - Starts FastAPI on uvicorn
- `playwright-proxy-client` -> `playwright_mcp_proxy.client:main` - Starts MCP stdio server

**Direct execution:**
- `uv run playwright-proxy-server` - Start HTTP server
- `uv run playwright-proxy-client` - Start MCP client
- `uv run pytest` - Run tests

## Platform Requirements

**Development:**
- Python >= 3.12 (3.14 recommended)
- Node.js + npx (for spawning Playwright MCP subprocess)
- uv package manager
- Playwright browsers installed (`npx @playwright/mcp@latest` handles this)

**Production:**
- Same as development (runs locally, not containerized)
- SQLite (file-based, no external database server)
- Port 34501 available for HTTP server
- Browser executable available for Playwright (Chrome by default)

---

*Stack analysis: 2026-03-09*
