# Codebase Structure

**Analysis Date:** 2026-03-09

## Directory Layout

```
playwright-mcp-proxy/
├── playwright_mcp_proxy/          # Main Python package
│   ├── __init__.py                # Package root, exports __version__
│   ├── config.py                  # Pydantic Settings configuration
│   ├── client/                    # MCP stdio client component
│   │   ├── __init__.py            # Exports main()
│   │   └── mcp_server.py         # MCP server (stdio) with tool definitions
│   ├── database/                  # SQLite persistence layer
│   │   ├── __init__.py
│   │   ├── schema.py             # DDL statements for all tables
│   │   └── operations.py         # Async CRUD via aiosqlite
│   ├── models/                    # Pydantic data models
│   │   ├── __init__.py
│   │   ├── api.py                # HTTP API request/response models
│   │   └── database.py           # Database record models
│   └── server/                    # FastAPI HTTP server component
│       ├── __init__.py            # Exports create_app(), main()
│       ├── app.py                 # FastAPI routes and app factory
│       ├── playwright_manager.py  # Subprocess lifecycle management
│       └── session_state.py       # Session state capture logic
├── tests/                         # pytest test suite
│   ├── __init__.py
│   ├── test_database.py          # Database CRUD tests
│   ├── test_diff.py              # Diff cursor and hash tests
│   ├── test_phase7_schema.py     # Session state schema tests
│   ├── test_phase7_startup_detection.py  # Startup detection tests
│   └── test_phase7_state_capture.py      # State capture tests
├── examples/                      # Manual test scripts (not automated)
│   ├── debug_playwright_response.py
│   ├── test_bug_fix.py
│   ├── test_click_error.py
│   ├── test_context_lines.py
│   ├── test_diff.py
│   ├── test_server.py
│   └── test_user_scenario.py
├── .planning/                     # GSD planning documents
│   └── codebase/                  # Codebase analysis docs
├── main.py                        # Placeholder entry point (unused)
├── pyproject.toml                 # Project metadata, deps, scripts, tool config
├── uv.lock                        # Dependency lockfile
├── .python-version                # Python version pin
├── .env.example                   # Example environment variables
├── .mcp.json                      # MCP configuration
├── CLAUDE.md                      # Claude Code project instructions
├── README.md                      # Project documentation
├── INSTALL.md                     # Installation guide
├── QUICKSTART.md                  # Quick start guide
├── TROUBLESHOOTING.md             # Troubleshooting guide
├── CHANGELOG.md                   # Version history
├── PHASE7_DESIGN.md               # Phase 7 design document
├── PHASE7_STATUS.md               # Phase 7 status tracker
├── LICENSE                        # MIT license
└── .gitignore                     # Git ignore rules
```

## Directory Purposes

**`playwright_mcp_proxy/`:**
- Purpose: Main Python package containing all application code
- Contains: Four sub-packages (client, server, database, models) plus config
- Key files: `__init__.py` (version), `config.py` (settings)

**`playwright_mcp_proxy/client/`:**
- Purpose: MCP stdio server that upstream clients (e.g., Claude Desktop) connect to
- Contains: Tool definitions and request handlers
- Key files: `mcp_server.py` (all tool definitions and `handle_tool_call()`)

**`playwright_mcp_proxy/server/`:**
- Purpose: FastAPI HTTP server managing the Playwright subprocess and persistence
- Contains: HTTP routes, subprocess management, session state
- Key files: `app.py` (routes), `playwright_manager.py` (subprocess lifecycle), `session_state.py` (state capture)

**`playwright_mcp_proxy/database/`:**
- Purpose: SQLite persistence layer with async operations
- Contains: Schema DDL and CRUD operations
- Key files: `schema.py` (table definitions), `operations.py` (all DB methods)

**`playwright_mcp_proxy/models/`:**
- Purpose: Pydantic models shared across components
- Contains: API models and database record models
- Key files: `api.py` (ProxyRequest, ProxyResponse, ResponseMetadata), `database.py` (Session, Request, Response, ConsoleLog, DiffCursor)

**`tests/`:**
- Purpose: Automated pytest test suite
- Contains: Unit tests using temporary SQLite databases
- Key files: `test_database.py`, `test_diff.py`, `test_phase7_*.py`

**`examples/`:**
- Purpose: Manual test scripts requiring a running server
- Contains: Python scripts that hit HTTP endpoints directly
- Not automated; run individually with `python examples/<script>.py`

## Key File Locations

**Entry Points:**
- `playwright_mcp_proxy/server/__init__.py`: Server entry via `main()` -- registered as `playwright-proxy-server` script
- `playwright_mcp_proxy/client/__init__.py`: Client entry via `main()` -- registered as `playwright-proxy-client` script
- `main.py`: Placeholder at project root (not used by either component)

**Configuration:**
- `playwright_mcp_proxy/config.py`: Pydantic Settings with `PLAYWRIGHT_PROXY_` env prefix
- `pyproject.toml`: Project metadata, dependencies, script entry points, Ruff and pytest config
- `.env.example`: Template for environment variables (existence noted only)
- `.python-version`: Pins Python version for the project

**Core Logic:**
- `playwright_mcp_proxy/server/app.py`: FastAPI app factory, all HTTP route handlers
- `playwright_mcp_proxy/server/playwright_manager.py`: Subprocess spawn, health monitoring, restart logic
- `playwright_mcp_proxy/client/mcp_server.py`: MCP tool definitions, tool call dispatch
- `playwright_mcp_proxy/database/operations.py`: All async database CRUD methods

**Testing:**
- `tests/test_database.py`: Database CRUD operation tests
- `tests/test_diff.py`: Diff cursor, hash comparison, read workflow tests
- `tests/test_phase7_schema.py`: Phase 7 session state schema tests
- `tests/test_phase7_startup_detection.py`: Startup detection tests
- `tests/test_phase7_state_capture.py`: State capture tests

## Naming Conventions

**Files:**
- snake_case for all Python modules: `mcp_server.py`, `playwright_manager.py`, `session_state.py`
- Test files prefixed with `test_`: `test_database.py`, `test_diff.py`
- Example scripts prefixed with `test_` or `debug_`: `test_server.py`, `debug_playwright_response.py`

**Directories:**
- snake_case for all package directories: `playwright_mcp_proxy/`, `client/`, `server/`, `database/`, `models/`
- Every package directory contains an `__init__.py`

**Modules:**
- One module per concern: `schema.py` for DDL, `operations.py` for CRUD, `app.py` for routes
- Models split by domain: `api.py` for HTTP models, `database.py` for DB record models

**Console Scripts:**
- Hyphenated names: `playwright-proxy-server`, `playwright-proxy-client`
- Defined in `pyproject.toml` under `[project.scripts]`

## Where to Add New Code

**New HTTP Endpoint:**
- Add route handler to `playwright_mcp_proxy/server/app.py`
- Add request/response models to `playwright_mcp_proxy/models/api.py`
- Add manual test script to `examples/`

**New MCP Tool:**
- Add `Tool` definition to the `TOOLS` list in `playwright_mcp_proxy/client/mcp_server.py`
- Add handler logic in `handle_tool_call()` in the same file
- For proxied tools: forward via `/proxy` endpoint
- For custom tools: implement with direct HTTP calls

**New Database Operation:**
- Add async method to `playwright_mcp_proxy/database/operations.py`
- Add Pydantic model to `playwright_mcp_proxy/models/database.py` if new record type
- If new table needed: add DDL to `playwright_mcp_proxy/database/schema.py`
- Add tests to `tests/test_database.py`

**New Database Table:**
- Add `CREATE TABLE` statement to `playwright_mcp_proxy/database/schema.py`
- Add record model to `playwright_mcp_proxy/models/database.py`
- Add CRUD methods to `playwright_mcp_proxy/database/operations.py`

**New Feature (multi-file):**
- Primary code: appropriate sub-package under `playwright_mcp_proxy/`
- Tests: `tests/test_<feature>.py`
- Manual test: `examples/test_<feature>.py`

**Utilities / Shared Helpers:**
- Place in `playwright_mcp_proxy/` at the package root level (alongside `config.py`)
- No dedicated `utils/` directory exists; create one if multiple utility modules are needed

## Special Directories

**`.planning/`:**
- Purpose: GSD planning and codebase analysis documents
- Generated: By Claude Code mapping commands
- Committed: Yes

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes, by `uv`
- Committed: No (in `.gitignore`)

**`.ruff_cache/`:**
- Purpose: Ruff linter cache
- Generated: Yes
- Committed: No (in `.gitignore`)

**`.pytest_cache/`:**
- Purpose: pytest cache for last-failed tracking
- Generated: Yes
- Committed: No (in `.gitignore`)

**`examples/`:**
- Purpose: Manual integration test scripts (require running server)
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-03-09*
