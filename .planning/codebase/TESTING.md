# Testing Patterns

**Analysis Date:** 2026-03-09

## Test Framework

**Runner:**
- pytest >= 8.3.0
- Config: `pyproject.toml` (`[tool.pytest.ini_options]`)

**Async Support:**
- pytest-asyncio >= 0.24.0
- `asyncio_mode = "auto"` — all async test functions are automatically detected without needing explicit markers (though existing tests still use `@pytest.mark.asyncio` decorators)

**Coverage:**
- pytest-cov >= 6.0.0

**Run Commands:**
```bash
uv run pytest                          # Run all tests
uv run pytest -v                       # Verbose output
uv run pytest --cov=playwright_mcp_proxy  # With coverage
uv run pytest tests/test_database.py   # Single file
uv run pytest tests/test_database.py::test_create_and_get_session  # Single test
```

## Test File Organization

**Location:** All tests live in `tests/` at project root (separate from source).

**Naming:** Files use `test_` prefix. Pattern: `test_{module_or_feature}.py`

**Structure:**
```
tests/
├── __init__.py                       # Package marker (docstring only)
├── test_database.py                  # Database CRUD operations (6 tests)
├── test_diff.py                      # Phase 2 diff/cursor logic (8 tests)
├── test_phase7_schema.py             # Phase 7 schema migrations (3 tests)
├── test_phase7_state_capture.py      # Session state capture/restore (8 tests)
├── test_phase7_startup_detection.py  # Startup detection & session recovery (7 tests)
```

**Test path config:** `testpaths = ["tests"]` in `pyproject.toml`

## Test Structure

**Suite Organization:**

Tests are flat functions (no classes). Each test is a standalone async function with a docstring:

```python
@pytest.mark.asyncio
async def test_create_and_get_session(db):
    """Test creating and retrieving a session."""
    session = Session(
        session_id="test-session-1",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    retrieved = await db.get_session("test-session-1")
    assert retrieved is not None
    assert retrieved.session_id == "test-session-1"
    assert retrieved.state == "active"
```

**Pattern:** Arrange-Act-Assert with inline setup. No `describe`/`context` nesting.

**Naming Convention:** `test_{action}_{subject}` or `test_{workflow}_{condition}`:
- `test_create_and_get_session`
- `test_diff_workflow_first_read`
- `test_capture_state_empty_cookies`
- `test_detect_orphaned_sessions_recoverable`

## Fixtures

**Database Fixture (shared pattern across `test_database.py` and `test_diff.py`):**

```python
@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    await init_database(db_path)
    database = Database(db_path)
    await database.connect()

    yield database

    await database.close()
    Path(db_path).unlink(missing_ok=True)
```

Key characteristics:
- Uses `tempfile.NamedTemporaryFile` for isolated SQLite DBs
- Runs full schema initialization via `init_database()`
- Yields a connected `Database` instance
- Cleans up: closes connection + deletes temp file

**No conftest.py:** The `db` fixture is duplicated in both `test_database.py` and `test_diff.py`. There is no shared `conftest.py`.

**Phase 7 tests use inline setup** instead of fixtures — each test creates its own temp DB with try/finally cleanup:

```python
@pytest.mark.asyncio
async def test_detect_orphaned_sessions_recoverable():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as f:
        db_path = f.name
    try:
        await init_database(db_path)
        db = Database(db_path)
        await db.connect()
        # ... test logic ...
        await db.close()
    finally:
        Path(db_path).unlink(missing_ok=True)
```

**When adding new tests:**
- For database tests: use the `db` fixture pattern
- For tests needing mocks: use inline setup (no fixture needed)
- Always use temp files for SQLite — never write to the project directory

## Mocking

**Framework:** `unittest.mock` (stdlib) — `MagicMock`, `AsyncMock`

**Primary use:** Mocking `PlaywrightManager` for session state tests.

**Pattern — Mock with side_effect routing:**

```python
from unittest.mock import AsyncMock, MagicMock

mock_playwright = MagicMock()
mock_playwright.send_request = AsyncMock()

async def mock_send_request(method, params):
    """Route mock responses based on function content."""
    if method != "tools/call":
        return {}
    function = params.get("arguments", {}).get("function", "")

    if "window.location.href" in function:
        return {"content": [{"type": "text", "text": "https://example.com/test"}]}
    if "document.cookie" in function:
        return {"content": [{"type": "text", "text": "session=abc123"}]}
    # ... more routes ...
    return {}

mock_playwright.send_request.side_effect = mock_send_request
```

**Pattern — Simple error mock:**

```python
mock_playwright = MagicMock()
mock_playwright.send_request = AsyncMock(side_effect=Exception("Connection failed"))
```

**What is mocked:**
- `PlaywrightManager.send_request` — the subprocess communication layer
- No HTTP/FastAPI mocking (no TestClient usage)

**What is NOT mocked:**
- SQLite database — always uses real temp DB
- Pydantic models — always instantiated with real data
- Hash computation (`compute_hash`) — tested directly

## Fixtures and Factories

**Test Data:** Created inline using Pydantic model constructors. No factory library.

```python
session = Session(
    session_id="test-session-1",
    created_at=datetime.now(),
    last_activity=datetime.now(),
    state="active",
)

request = Request(
    ref_id="test-ref-1",
    session_id="test-session-1",
    tool_name="browser_navigate",
    params='{"url": "https://example.com"}',
    timestamp=datetime.now(),
)
```

**ID convention:** Test data uses `test-session-{N}`, `test-ref-{N}` pattern for identifiers.

**No shared factories or builders.** Each test constructs its own data.

## Coverage

**Requirements:** No enforced coverage threshold.

**View Coverage:**
```bash
uv run pytest --cov=playwright_mcp_proxy
uv run pytest --cov=playwright_mcp_proxy --cov-report=html  # HTML report
```

## Test Types

**Unit Tests (all current tests):**
- Database CRUD operations against real SQLite
- Hash computation logic
- Diff cursor lifecycle
- Session state capture/restore with mocked subprocess
- Schema validation and migration compatibility

**Integration Tests:**
- None in `tests/`. Manual integration tests exist in `examples/` directory but require a running server.

**E2E Tests:**
- Not automated. Manual scripts in `examples/`:
  - `examples/test_server.py` — HTTP endpoint testing
  - `examples/test_diff.py` — Diff functionality
  - `examples/test_user_scenario.py` — Full user workflow
  - `examples/test_click_error.py` — Error scenario
  - `examples/test_context_lines.py` — Context line testing
  - `examples/test_bug_fix.py` — Bug fix verification

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_something(db):
    result = await db.some_async_method("arg")
    assert result is not None
```

**Error Testing:**
```python
@pytest.mark.asyncio
async def test_capture_state_error_handling():
    mock_playwright = MagicMock()
    mock_playwright.send_request = AsyncMock(side_effect=Exception("Connection failed"))

    manager = SessionStateManager(mock_playwright)
    snapshot = await manager.capture_state("test-session-error")

    # Verify graceful handling — returns None, does not raise
    assert snapshot is None
```

**Persistence/Restart Testing:**
```python
@pytest.mark.asyncio
async def test_diff_cursor_persists_across_restart(db):
    cursor = DiffCursor(ref_id="test-ref-7", ...)
    await db.upsert_diff_cursor(cursor)

    # Close and reopen database (simulating restart)
    await db.close()
    await db.connect()

    retrieved = await db.get_diff_cursor("test-ref-7")
    assert retrieved is not None
```

**Workflow Testing (multi-step):**

Tests that verify a complete workflow (create prerequisites, perform action, verify outcome):

```python
@pytest.mark.asyncio
async def test_diff_workflow_first_read(db):
    # 1. Create session → request → response (prerequisites)
    # 2. Verify no cursor exists
    # 3. Simulate first read (create cursor with hash)
    # 4. Verify cursor was created with correct hash
```

## Coverage Gaps

**Critical — No tests for:**

| Component | File | Lines | Gap |
|-----------|------|-------|-----|
| HTTP Server (FastAPI) | `playwright_mcp_proxy/server/app.py` | 691 | No endpoint tests. No TestClient. Zero coverage of `/proxy`, `/content/{ref_id}`, `/console/{ref_id}`, `/sessions`, `/health` endpoints |
| Playwright Manager | `playwright_mcp_proxy/server/playwright_manager.py` | 294 | No tests for subprocess spawning, health check loop, auto-restart, graceful shutdown, JSON-RPC communication |
| MCP Client | `playwright_mcp_proxy/client/mcp_server.py` | 301 | No tests for tool definitions, `handle_tool_call()` routing, stdio MCP protocol handling, HTTP forwarding |
| Configuration | `playwright_mcp_proxy/config.py` | 89 | No tests for settings loading, env var parsing, defaults |

**Medium — Partial coverage:**

| Component | File | Gap |
|-----------|------|-----|
| Database operations | `playwright_mcp_proxy/database/operations.py` (528 lines) | Phase 7 snapshot operations tested, but `update_session_state`, `save_session_snapshot`, `get_session_snapshots`, `cleanup_old_snapshots` only tested indirectly through startup detection tests. No edge case testing (concurrent writes, constraint violations, large data). |
| Session state | `playwright_mcp_proxy/server/session_state.py` (252 lines) | Capture/restore tested with mocks but no integration test verifying actual Playwright interaction |

**Structural issues:**
- Duplicated `db` fixture across `test_database.py` and `test_diff.py` — should be in `conftest.py`
- Phase 7 tests use inline DB setup instead of shared fixture
- `@pytest.mark.asyncio` decorators are redundant given `asyncio_mode = "auto"` config
- No test markers for categorization (e.g., `@pytest.mark.slow`, `@pytest.mark.integration`)
- No parametrized tests — repetitive setup could be reduced with `@pytest.mark.parametrize`

---

*Testing analysis: 2026-03-09*
