# Coding Conventions

**Analysis Date:** 2026-03-09

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `mcp_server.py`, `playwright_manager.py`, `session_state.py`
- Test files prefixed with `test_`: `test_database.py`, `test_diff.py`, `test_phase7_schema.py`
- Feature-specific tests use `test_{phase}_{feature}.py` pattern: `test_phase7_state_capture.py`

**Functions:**
- Use `snake_case` for all functions and methods
- Async functions use `async def` consistently (no sync wrappers around async operations)
- Private methods prefixed with underscore: `_health_check_loop()`, `_attempt_restart()`, `_send_initialize()`, `_extract_evaluate_result()`, `_parse_cookie_string()`, `_read_line_chunked()`
- Database operations named as `verb_noun`: `create_session()`, `get_response()`, `update_session_state()`, `delete_diff_cursor()`, `upsert_diff_cursor()`
- Compound operations named descriptively: `create_console_logs_batch()`, `get_latest_session_snapshot()`, `cleanup_old_snapshots()`

**Variables:**
- Use `snake_case` for all variables
- Module-level globals use `snake_case` without prefix: `playwright_manager`, `database`, `snapshot_task`, `current_session_id`
- Private instance variables prefixed with underscore: `self._connection`, `self._health_check_task`, `self._message_id`, `self._lock`
- Type annotations with `Optional` from `typing` (not `X | None`) in most files, except `client/mcp_server.py` which uses `str | None`

**Classes:**
- Use `PascalCase`: `Database`, `PlaywrightManager`, `SessionStateManager`, `Settings`
- Pydantic models use `PascalCase` matching the domain concept: `Session`, `Request`, `Response`, `ConsoleLog`, `DiffCursor`, `SessionSnapshot`
- API models use descriptive compound names: `ProxyRequest`, `ProxyResponse`, `ResponseMetadata`, `ErrorResponse`

**Constants:**
- Use `UPPER_SNAKE_CASE` for module-level constants: `SCHEMA`, `TOOLS`

**Modules/Packages:**
- Use `snake_case` for package directories: `playwright_mcp_proxy`, `database`, `server`, `client`, `models`

## Code Style

**Formatting:**
- Ruff is the sole formatter and linter
- Config in `pyproject.toml`: `line-length = 100`, `target-version = "py312"`
- E501 (line too long) is explicitly ignored -- lines can exceed 100 chars

**Linting:**
- Ruff lint rules selected: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `N` (pep8-naming), `W` (pycodestyle warnings)
- Run check: `uv run ruff check .`
- Run auto-fix: `uv run ruff check --fix .`

**String Formatting:**
- Use f-strings for string interpolation throughout: `f"Created session {session_id}"`
- Use triple-quoted multiline strings for SQL: `"""INSERT INTO sessions ..."""`
- Use regular strings for simple values

**Trailing Commas:**
- Always use trailing commas in multi-line function calls, tuples, and lists
- Example from `database/operations.py`:
```python
await self.conn.execute(
    "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
    (datetime.now().isoformat(), session_id),  # trailing comma
)
```

## Import Organization

**Order (enforced by Ruff `I` rule):**
1. Standard library imports (`asyncio`, `hashlib`, `json`, `logging`, `time`, `uuid`, `traceback`)
2. Third-party imports (`aiosqlite`, `fastapi`, `httpx`, `mcp`, `pydantic`, `pydantic_settings`)
3. Local/relative imports (`from ..config import settings`, `from ..models.database import ...`)

**Style:**
- Use `from X import Y` for specific items, not `import X` (except for standard library modules like `asyncio`, `json`, `logging`)
- Relative imports within the package: `from ..config import settings`, `from ..models.database import Session`
- Explicit re-exports in `__init__.py` with `__all__` list:
```python
# playwright_mcp_proxy/database/__init__.py
from .operations import Database
from .schema import init_database
__all__ = ["init_database", "Database"]
```

**Path Aliases:**
- None. All imports use relative paths within the package.

## Error Handling

**Patterns:**

1. **Return None for not-found lookups** (database layer):
```python
# playwright_mcp_proxy/database/operations.py
async def get_session(self, session_id: str) -> Optional[Session]:
    async with self.conn.execute(...) as cursor:
        row = await cursor.fetchone()
        if not row:
            return None
        return Session(...)
```

2. **Raise HTTPException for HTTP errors** (server layer):
```python
# playwright_mcp_proxy/server/app.py
if not session:
    raise HTTPException(status_code=404, detail="Session not found")
if session.state != "active":
    raise HTTPException(status_code=400, detail=f"Session is {session.state}")
```

3. **Broad except with logging and continue** (background tasks):
```python
# playwright_mcp_proxy/server/app.py
except asyncio.CancelledError:
    logger.info("Periodic snapshot task cancelled")
    break
except (KeyError, IndexError) as e:
    logger.error(f"Error in periodic snapshot task - {type(e).__name__} with key/index: {e}")
except Exception as e:
    logger.error(f"Error in periodic snapshot task: {type(e).__name__}: {e}")
```

4. **Return error responses instead of raising** (MCP client):
```python
# playwright_mcp_proxy/client/mcp_server.py
except httpx.HTTPError as e:
    logger.error(f"HTTP error calling tool {name}: {e}")
    error_str = str(e)[:200]
    return [TextContent(type="text", text=f"HTTP error: {error_str}")]
```

5. **Error truncation for MCP protocol limits:**
```python
# playwright_mcp_proxy/server/app.py
def truncate_error(error_msg: str, max_length: int = 500) -> str:
    if len(error_msg) <= max_length:
        return error_msg
    return error_msg[:max_length] + f"... (truncated, {len(error_msg)} total chars)"
```

6. **Re-raise HTTPException in mixed try/except blocks:**
```python
except HTTPException:
    raise
except Exception as e:
    logger.error(f"Error resuming session {session_id}: {e}")
    raise HTTPException(status_code=500, detail=f"Failed to resume session: {str(e)}")
```

**Convention:** Database layer returns `None` for missing data. Server layer converts to `HTTPException`. Client layer catches all exceptions and returns `TextContent` error messages.

## Logging

**Framework:** Python standard library `logging`

**Setup pattern:**
```python
# Module-level logger (used in most files)
logger = logging.getLogger(__name__)

# Root config only in app.py entry point
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
```

**NOTE:** `client/mcp_server.py` also calls `logging.basicConfig(level=logging.INFO)` at module level -- this is a separate entry point.

**Log level usage:**
- `logger.info()` for lifecycle events: startup, shutdown, session creation, state changes
- `logger.debug()` for operational details: health checks, snapshot captures, stderr output
- `logger.warning()` for degraded states: health check failures, capture failures
- `logger.error()` for failures: subprocess crashes, restore failures, unhandled exceptions

**Log message pattern:**
- Use f-strings with descriptive context: `f"Session {session.session_id}: Recent snapshot ({int(age_seconds)}s old), marking as recoverable"`
- Include `type(e).__name__` for exception type clarity: `f"Error processing session {session.session_id}: {type(e).__name__}: {e}"`
- Truncate potentially large error messages before logging: `logger.error(f"Error proxying request: {error_str[:500]}")`

**Anti-pattern present:** Some methods in `database/operations.py` (lines 131-156, 401-429) use inline `import logging` and `logging.getLogger(__name__)` inside loops for debug purposes. This is debug code that should use the module-level logger.

## Pydantic Model Conventions

**Base class:** All models extend `pydantic.BaseModel`

**Field definitions:**
- Always use `Field()` with `description` parameter for documentation
- Required fields use `Field(...)` (ellipsis)
- Optional fields use `Field(None, description=...)` or `Field(default=..., description=...)`
- Default factories for timestamps: `Field(default_factory=datetime.now, description=...)`
- Dict defaults use factory: `Field(default_factory=dict, description=...)`

**Example pattern from `playwright_mcp_proxy/models/api.py`:**
```python
class ProxyRequest(BaseModel):
    """Request to the proxy server."""
    session_id: str = Field(..., description="Session UUID")
    tool: str = Field(..., description="Tool name to call")
    params: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    request_id: Optional[str] = Field(None, description="Optional request UUID")
```

**Settings model** (`playwright_mcp_proxy/config.py`):
- Extends `pydantic_settings.BaseSettings`
- Uses inner `class Config` (not `model_config`) with `env_prefix`, `env_file`, `env_file_encoding`
- Singleton pattern: global `settings = Settings()` at module level
- Imported everywhere as `from ..config import settings`

**Database models vs API models:**
- Database models in `playwright_mcp_proxy/models/database.py` -- represent SQLite rows
- API models in `playwright_mcp_proxy/models/api.py` -- represent HTTP request/response shapes
- Both use `BaseModel` with `Field()` descriptors
- Database models store JSON as `str` fields (not parsed): `params: str`, `cookies: Optional[str]`

**No ORM mapping:** Models are manually constructed from `aiosqlite.Row` dicts in `database/operations.py`. There is no automatic ORM or model binding.

## SQL Conventions

**Schema definition** (`playwright_mcp_proxy/database/schema.py`):
- Single `SCHEMA` constant with all DDL as a triple-quoted string
- All tables use `CREATE TABLE IF NOT EXISTS`
- All indexes use `CREATE INDEX IF NOT EXISTS`
- Primary keys are `TEXT` (UUIDs) or `INTEGER PRIMARY KEY AUTOINCREMENT`
- Foreign keys declared but SQLite enforcement depends on `PRAGMA foreign_keys`
- CHECK constraints for enum-like columns: `CHECK(state IN ('active', 'closed', 'error', ...))`
- Comments in SQL use `--` prefix for table-level documentation
- Index naming: `idx_{table}_{column}`

**Query style** (`playwright_mcp_proxy/database/operations.py`):
- Use parameterized queries with `?` placeholders (never string interpolation)
- Multi-line SQL uses triple-quoted strings indented within the method
- Use `async with self.conn.execute(...) as cursor` for reads
- Use `await self.conn.execute(...)` followed by `await self.conn.commit()` for writes
- Every write operation commits immediately (no batched transactions)
- `UPSERT` pattern: `INSERT ... ON CONFLICT(pk) DO UPDATE SET ...`

**Row-to-model mapping:**
```python
# Manual mapping from Row dict to Pydantic model
return Session(
    session_id=row["session_id"],
    created_at=datetime.fromisoformat(row["created_at"]),
    last_activity=datetime.fromisoformat(row["last_activity"]),
    state=row["state"],
    ...
)
```

**Timestamps:** Stored as ISO format strings via `.isoformat()`, parsed back with `datetime.fromisoformat()`

## Module Design Patterns

**Package structure:**
- Each subpackage has `__init__.py` with explicit `__all__` re-exports
- `__init__.py` is the public API; internal modules are implementation details

**Docstrings:**
- Every module has a one-line module docstring: `"""Database operations."""`
- Every class has a one-line class docstring: `"""Database operations wrapper."""`
- Functions/methods use Google-style docstrings with Args/Returns sections for complex methods
- Simple methods use one-line docstrings: `"""Open database connection."""`

**Example from `playwright_mcp_proxy/server/session_state.py`:**
```python
async def capture_state(self, session_id: str) -> Optional[SessionSnapshot]:
    """
    Capture current browser state for a session.

    Extracts:
    - Current URL
    - Cookies
    - localStorage
    - sessionStorage
    - Viewport size

    Args:
        session_id: Session ID to capture state for

    Returns:
        SessionSnapshot with captured state, or None if capture fails
    """
```

**Global state pattern** (`playwright_mcp_proxy/server/app.py`):
- Module-level globals declared with type annotations: `playwright_manager: PlaywrightManager`
- Initialized in `lifespan()` context manager using `global` keyword
- Accessed directly in route handlers (no dependency injection)

**Class design:**
- Classes with managed resources use explicit `connect()`/`close()` or `start()`/`stop()` lifecycle methods (not context managers)
- `Database` class: `connect()` + `close()` with `@property conn` that raises if not connected
- `PlaywrightManager` class: `start()` + `stop()` with `is_healthy` property

**Entry points:**
- Each component has a `main()` function at the bottom of its module
- Also has `if __name__ == "__main__": main()` guard
- Package entry points defined in `pyproject.toml` `[project.scripts]`

**FastAPI app pattern:**
- Factory function `create_app()` returns configured `FastAPI` instance
- Routes defined as inner functions within `create_app()` using decorators
- `@asynccontextmanager` lifespan for startup/shutdown
- Uvicorn invoked with `factory=True` flag

**Async-first:**
- All I/O operations are async (`await`)
- `asyncio.Lock()` for concurrency control in `PlaywrightManager`
- `asyncio.create_task()` for background tasks (health check, stderr monitor, periodic snapshots)
- `asyncio.CancelledError` handled explicitly for graceful task shutdown

**Type annotations:**
- All function signatures have type annotations for parameters and return values
- Use `Optional[X]` from `typing` (Python 3.12 style `X | None` used only in `client/mcp_server.py`)
- Use built-in generics: `dict[str, Any]`, `list[Session]`, `tuple`
- `deque` from `collections` with `maxlen` for bounded collections

---

*Convention analysis: 2026-03-09*
