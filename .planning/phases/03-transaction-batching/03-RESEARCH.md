# Phase 3: Transaction Batching - Research

**Researched:** 2026-03-10
**Domain:** SQLite transaction batching with aiosqlite / Python sqlite3
**Confidence:** HIGH

## Summary

Phase 3 reduces SQLite commit overhead in the `/proxy` endpoint from 4 commits per request down to 2. The codebase uses `aiosqlite 0.21.0` wrapping Python's `sqlite3` module. Python's sqlite3 module automatically opens a transaction on the first DML statement when `isolation_level` is not `None` (which is the default — `isolation_level = ''`, meaning deferred). Multiple `execute()` calls after the transaction begins all accumulate in the same open transaction until `commit()` is called. This means batching is mechanically straightforward: remove intermediate `commit()` calls from individual `Database` methods and let the caller issue a single `commit()` at the boundary.

The current proxy request success path issues 4 commits: (1) `create_request`, (2) `update_session_activity`, (3) `create_response`, (4) `create_console_logs_batch`. The requirement mandates exactly 2: one commit after the request record (pre-RPC audit trail), and one commit for all post-RPC writes together (response + session activity update + console logs). The audit trail requirement is non-negotiable — a failed Playwright RPC must still have the request row durable in the database.

The implementation pattern is: add batching-aware variants to `Database` (methods that execute but do not commit) and add an explicit `commit()` to `app.py` at each of the two boundary points. No new dependencies, no schema changes, no architectural changes.

**Primary recommendation:** Add `_execute_no_commit` variants for the three post-RPC operations (`create_response`, `update_session_activity`, `create_console_logs_batch`) and call `conn.commit()` once in `app.py` after all three are executed.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PERF-01 | Related database operations batched into single transactions (reduce 3+ commits per request to 2) | aiosqlite's sqlite3 foundation accumulates DML in open transaction; removing intermediate commits and adding two explicit boundary commits achieves exactly this |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| aiosqlite | 0.21.0 | Async SQLite wrapper already in use | Already the project's DB layer; no new dep needed |
| sqlite3 (stdlib) | bundled | Underlying transaction engine | Default `isolation_level=''` enables deferred transaction grouping |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-asyncio | >=1.0.0 | Async test support | All test functions are already async; `asyncio_mode = auto` |
| pytest | >=8.3.0 | Test framework | Existing test infrastructure |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Method-level commit removal | `isolation_level=None` (autocommit) + explicit BEGIN/COMMIT | Autocommit mode requires explicit BEGIN before every write; more invasive, breaks existing tests |
| Method-level commit removal | Context-manager transaction wrapper | Cleaner API but overengineered for 2 boundaries; adds abstraction complexity |

**Installation:**
No new packages required. Everything needed is already installed.

## Architecture Patterns

### Recommended Project Structure
No structural changes needed. Changes are confined to:
```
playwright_mcp_proxy/
├── database/
│   └── operations.py     # add no-commit variants for post-RPC ops
└── server/
    └── app.py            # restructure proxy_request to 2-commit boundary
```

### Pattern 1: No-Commit Method Variants
**What:** Add `_no_commit` suffixed methods (or a `commit` boolean parameter) for the operations that participate in the post-RPC batch. The method performs the `execute()` / `executemany()` but skips `await self.conn.commit()`.

**When to use:** When a caller needs to group multiple DB writes under a single future commit.

**Example:**
```python
# Source: aiosqlite 0.21.0 behavior — DML accumulates in open transaction
async def create_response_no_commit(self, response: Response) -> None:
    """Insert response row WITHOUT committing (caller commits)."""
    await self.conn.execute(
        """
        INSERT INTO responses
        (ref_id, status, result, page_snapshot, console_logs, error_message, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            response.ref_id,
            response.status,
            response.result,
            response.page_snapshot,
            response.console_logs,
            response.error_message,
            response.timestamp.isoformat(),
        ),
    )
    # No commit() — caller batches this with other writes

async def update_session_activity_no_commit(self, session_id: str) -> None:
    """Update session last_activity WITHOUT committing (caller commits)."""
    await self.conn.execute(
        "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
        (datetime.now().isoformat(), session_id),
    )

async def create_console_logs_batch_no_commit(self, logs: list[ConsoleLog]) -> None:
    """Batch insert console logs WITHOUT committing (caller commits)."""
    if not logs:
        return
    await self.conn.executemany(
        """
        INSERT INTO console_logs (ref_id, level, message, timestamp, location)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (log.ref_id, log.level, log.message, log.timestamp.isoformat(), log.location)
            for log in logs
        ],
    )
```

### Pattern 2: Two-Boundary Commit in proxy_request
**What:** The `proxy_request` handler in `app.py` issues exactly 2 commits, with the Playwright RPC in between.

**When to use:** Always for the `/proxy` endpoint.

**Example:**
```python
# Source: derived from success criteria in ROADMAP.md Phase 3
async def proxy_request(request: ProxyRequest):
    # ... session validation ...

    # Pre-RPC: persist request record and commit immediately (audit trail)
    db_request = Request(...)
    await database.create_request(db_request)          # commits internally (COMMIT 1)

    try:
        result = await playwright_manager.send_request(...)

        # Post-RPC: batch all writes, single commit (COMMIT 2)
        db_response = Response(...)
        await database.create_response_no_commit(db_response)

        if console_logs_data:
            entries = _parse_console_blob(console_logs_data)
            if entries:
                logs = [ConsoleLog(...) for entry in entries]
                await database.create_console_logs_batch_no_commit(logs)

        await database.update_session_activity_no_commit(request.session_id)
        await database.conn.commit()                   # COMMIT 2 — all post-RPC writes

        # ... build and return ProxyResponse ...

    except Exception as e:
        # Error path: response + session state change in one commit
        db_response = Response(ref_id=ref_id, status="error", ...)
        await database.create_response_no_commit(db_response)
        await database.update_session_state_no_commit(request.session_id, "error")
        await database.conn.commit()                   # COMMIT 2 on error path
        # ... return error ProxyResponse ...
```

**Critical note on `update_session_activity` timing:** Currently `update_session_activity` is called BEFORE the Playwright RPC (line 497 in app.py). The requirement says post-RPC writes are batched together. Moving `update_session_activity` to the post-RPC batch is correct — the audit requirement only protects the `request` record, not the session timestamp.

### Anti-Patterns to Avoid
- **Calling `conn.commit()` inside individual `_no_commit` methods:** This defeats the entire purpose; no-commit variants must never commit.
- **Removing the pre-RPC `create_request` commit:** The audit trail requirement requires request to be durable before the RPC. The first commit must remain.
- **Using `isolation_level=None` (autocommit):** This would require explicit `BEGIN` before every group of writes and would invalidate all existing test assumptions.
- **Adding a context manager abstraction:** Adds complexity for a 2-boundary problem; direct method variants are simpler and the diff is reviewable in one pass.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Transaction grouping | Custom transaction queue / unit-of-work | aiosqlite's native DML accumulation (default isolation_level) | sqlite3 already groups DML under open transaction; just skip intermediate commits |
| Rollback on error | Manual state tracking | Python try/except + `conn.rollback()` | sqlite3 rolls back automatically on connection close, but explicit rollback in except block is cleaner |
| Commit counting in tests | Mock/spy framework | Direct DB query after test to verify state | Query the rows directly; commit count is an implementation detail, row durability is the observable outcome |

**Key insight:** Python's sqlite3 in deferred isolation mode (`isolation_level=''`) is already a transaction grouper. The current code adds unnecessary commit overhead by calling `commit()` after every single write. The fix is purely subtractive: remove the excess commits.

## Common Pitfalls

### Pitfall 1: Forgetting `conn.commit()` in the error path
**What goes wrong:** The success path gets its post-RPC batch commit, but the error-path writes (`create_response` error record + `update_session_state` to 'error') are left uncommitted. They are lost when the connection is next used because sqlite3 issues an implicit BEGIN and the writes are still open.
**Why it happens:** The error path is written in the `except` block and easy to overlook when restructuring.
**How to avoid:** Treat the error path as its own second-commit point. Add explicit `await database.conn.commit()` in the except block after the error writes.
**Warning signs:** Tests that verify error response is persisted will fail intermittently or not at all.

### Pitfall 2: Exposing `database.conn` directly in app.py
**What goes wrong:** `app.py` accessing `database.conn.commit()` directly couples the server layer to the database internals. If the `Database` class is ever refactored (e.g., connection pooling), this breaks.
**Why it happens:** The simplest approach to batch-commit is to call `conn.commit()` directly from the caller.
**How to avoid:** Add a `commit()` method to the `Database` class that delegates to `self.conn.commit()`. This keeps the abstraction clean.
**Warning signs:** Direct attribute chaining `database.conn.commit()` in app.py.

### Pitfall 3: `update_session_activity` before RPC causes an extra pre-RPC commit
**What goes wrong:** Current code calls `update_session_activity()` BEFORE the Playwright RPC (line 497 in app.py). This is a second pre-RPC commit. Moving it to the post-RPC batch eliminates the extra pre-RPC commit, bringing pre-RPC total to exactly 1.
**Why it happens:** The original code placed session activity update before the RPC as a "housekeeping" step.
**How to avoid:** Move `update_session_activity` to the post-RPC batch. A session timestamp update does not need to survive before the RPC completes.
**Warning signs:** Commit count remains at 3+ even after introducing no-commit variants.

### Pitfall 4: `get_console_error_count` query before `commit()`
**What goes wrong:** `error_count = await database.get_console_error_count(ref_id)` is called AFTER `create_console_logs_batch` but BEFORE the batch commit. SQLite reads within the same connection will see uncommitted writes (same connection sees its own open transaction), so the count will be correct. However, if this ordering is misunderstood, future developers might move the commit before the count query, which is unnecessary.
**Why it happens:** SQLite's read-your-own-writes within the same connection is sometimes surprising.
**How to avoid:** Document the ordering explicitly. The count query is safe before or after commit (same connection), but must be after the batch insert.
**Warning signs:** None — this is safe, just needs clear comments.

## Code Examples

Verified patterns from official sources:

### Adding a Public commit() to Database
```python
# Source: aiosqlite 0.21.0 Connection.commit() signature
async def commit(self) -> None:
    """Commit the current transaction."""
    await self.conn.commit()
```

### Checking in_transaction in tests
```python
# Source: aiosqlite 0.21.0 — in_transaction proxies sqlite3.Connection.in_transaction
assert db.conn.in_transaction  # True after execute, before commit
await db.commit()
assert not db.conn.in_transaction  # False after commit
```

### Test: request durability before RPC (audit trail)
```python
# Verify request row exists in DB before any response is written
await db.create_request(db_request)
# (simulated: no playwright RPC here)
retrieved = await db.get_request(ref_id)
assert retrieved is not None  # request is durable post-commit
```

### Test: post-RPC batch commit
```python
# Verify all post-RPC writes atomically visible after single commit
await db.create_response_no_commit(response)
await db.update_session_activity_no_commit(session_id)
# Before commit: rows not yet visible to external connection
# After commit: all visible atomically
await db.commit()
resp = await db.get_response(ref_id)
assert resp is not None
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One `commit()` per `Database` method | Batch commit at caller boundary | Phase 3 (this work) | Reduces commits from 4 to 2 per proxy request |

**Deprecated/outdated:**
- Per-method `await self.conn.commit()` in `create_response`, `update_session_activity`, `create_console_logs_batch`: replaced by no-commit variants + explicit boundary commit in app.py.

## Open Questions

1. **Should `create_console_log` (singular) get a no-commit variant?**
   - What we know: `create_console_log` (singular) is defined in operations.py but is not called in the proxy request path (only `create_console_logs_batch` is used).
   - What's unclear: Whether Phase 4 or future work will use the singular method in a batch context.
   - Recommendation: Leave the singular method as-is (it commits); add no-commit variant only for `create_console_logs_batch`. Can revisit in Phase 4.

2. **Should the Database class expose `in_transaction` property?**
   - What we know: `aiosqlite.Connection.in_transaction` exists and works.
   - What's unclear: Whether tests need to assert on transaction state vs. asserting on row durability.
   - Recommendation: Expose it passthrough (`@property def in_transaction: return self.conn.in_transaction`) for testability; tests for PERF-01 can assert durability via row queries rather than transaction state.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3+ with pytest-asyncio 1.0+ |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| Quick run command | `uv run pytest tests/test_transaction_batching.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERF-01 | Request record is durable (committed) before Playwright RPC fires | unit | `uv run pytest tests/test_transaction_batching.py::test_request_committed_before_rpc -x` | Wave 0 |
| PERF-01 | Failed RPC still has request record in DB | unit | `uv run pytest tests/test_transaction_batching.py::test_request_durable_on_rpc_failure -x` | Wave 0 |
| PERF-01 | Success path: response + session activity + console logs all written in single post-RPC commit | unit | `uv run pytest tests/test_transaction_batching.py::test_post_rpc_writes_batch_committed -x` | Wave 0 |
| PERF-01 | Total commit count per success path = 2 | unit | `uv run pytest tests/test_transaction_batching.py::test_commit_count_success_path -x` | Wave 0 |
| PERF-01 | Error path: error response + session state update in single post-RPC commit | unit | `uv run pytest tests/test_transaction_batching.py::test_error_path_batch_committed -x` | Wave 0 |
| PERF-01 | create_response_no_commit does not auto-commit | unit | `uv run pytest tests/test_transaction_batching.py::test_no_commit_methods_do_not_commit -x` | Wave 0 |
| PERF-01 | Existing test suite still passes (no regressions) | regression | `uv run pytest` | existing |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_transaction_batching.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_transaction_batching.py` — covers PERF-01 (all cases above); does not exist yet, created in Wave 0 task

*(Existing test infrastructure — `tests/test_database.py`, `tests/test_diff.py`, `tests/test_bugs.py` — covers prior phases and will serve as regression baseline.)*

## Sources

### Primary (HIGH confidence)
- aiosqlite 0.21.0 source (inspected via `uv run python -c "import inspect; ..."`) — `Connection.commit()`, `Connection.rollback()`, `Connection.in_transaction`, default `isolation_level`
- Python stdlib sqlite3 docs (built-in knowledge, confirmed by live inspection) — transaction behavior with default `isolation_level=''`
- Live aiosqlite tests (ran in project venv) — confirmed DML accumulation in open transaction, single-commit behavior

### Secondary (MEDIUM confidence)
- Project source: `playwright_mcp_proxy/database/operations.py` — current per-method commit pattern
- Project source: `playwright_mcp_proxy/server/app.py` (lines 465–597) — current proxy_request 4-commit flow
- Project source: `tests/test_database.py`, `tests/test_bugs.py` — test patterns and fixture shapes

### Tertiary (LOW confidence)
- None. All claims verified against live code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — aiosqlite 0.21.0 confirmed installed, isolation_level behavior verified live
- Architecture: HIGH — current commit sequence counted from actual source, batch pattern verified with live Python test
- Pitfalls: HIGH — derived from reading actual code paths in operations.py and app.py

**Research date:** 2026-03-10
**Valid until:** 2026-09-10 (stable aiosqlite API, unlikely to change)
