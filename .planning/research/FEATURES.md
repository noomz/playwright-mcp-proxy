# Feature Landscape

**Domain:** Python async MCP proxy -- tech debt cleanup and modernization
**Researched:** 2026-03-09

## Table Stakes

Features that must be fixed. These are bugs, data corruption risks, or broken promises in the current API.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Fix `str(params)` to `json.dumps(params)` | Stored params are currently undeserializable Python repr, not JSON. Data is write-only. | Low | One-line change in `app.py:435`. Replace `str(request.params)` with `json.dumps(request.params)`. Import json is already present. |
| Fix hardcoded `console_error_count = 0` | API promises error count in `ResponseMetadata` but always returns 0. Clients cannot trust the field. | Low | After `create_response`, parse `console_logs_data` (JSON blob) and count entries with `level == "error"`. The existing `get_console_error_count()` DB method queries the normalized table which is rarely populated, so parse the blob inline instead. |
| Fix console log level filtering in fallback path | `level` query parameter is silently ignored for the common case (blob-only storage). Users get all logs regardless of filter. | Low-Med | Parse the JSON blob in `app.py:669` fallback, filter entries by level, then format. Blob format is typically a JSON array of `{type, text}` objects from Playwright. |
| Add `pydantic-settings` to pyproject.toml | Fresh installs can fail. Missing explicit dependency. | Low | Add `pydantic-settings>=2.0.0` to `[project.dependencies]`. |
| Pin `@playwright/mcp` version | `@latest` means any npm publish can silently break the entire system. | Low | Change default in `config.py` from `@playwright/mcp@latest` to a pinned version (e.g., `@playwright/mcp@0.0.18` or whatever is currently installed). |
| Remove debug logging in `operations.py` | Field-by-field iteration with inline `import logging` in production hot path. Performance overhead on every row read. | Low | Delete the debug loops in `list_sessions()` (lines 121-156) and `get_latest_session_snapshot()` (lines 401-429). Keep the direct Session/SessionSnapshot construction. |

## Differentiators

Improvements that make the system more correct, performant, or maintainable. Not broken today, but clearly suboptimal.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Fix JS injection in `session_state.py` restore | f-string interpolation of user-controlled data into JS. Current escaping misses backticks, `${}`, newlines. While data is self-generated, defense in depth matters. | Medium | The Playwright MCP `browser_evaluate` tool accepts a `function` field. The safe approach: serialize the entire storage object to JSON, pass it as a string literal inside a self-contained JS function that parses and restores. E.g., `"() => { const data = JSON.parse('...escaped...'); Object.entries(data).forEach(([k,v]) => localStorage.setItem(k,v)); }"`. Use `json.dumps()` for the inner string (which handles all escaping correctly). **Note:** Playwright's native `evaluate(fn, arg)` pattern may not be available through the MCP stdio protocol -- the MCP tool schema only exposes `function` as a string, not a separate `arg` parameter. Verify the schema before assuming arg-passing is supported. |
| Batch DB operations into transactions | 3+ commits per proxy request, 3+ commits per snapshot cycle. Unnecessary fsync overhead. | Medium | Add a `transaction()` async context manager to the `Database` class that defers `commit()` to context exit. Pattern: `async with db.transaction(): await db.create_request(...); await db.create_response(...); await db.update_session_activity(...)`. Implementation: set a `_in_transaction` flag, skip individual commits when true, commit on `__aexit__`. aiosqlite uses Python's sqlite3 module which defaults to deferred transactions -- just removing intermediate commits and calling commit once at the end is sufficient. |
| Combine 5 sequential `browser_evaluate` calls into 1 | `capture_state()` makes 5 sequential RPCs through the asyncio-locked subprocess pipe. Each waits for full round-trip. | Medium | Replace 5 calls with a single `browser_evaluate` that returns a JSON object: `"() => JSON.stringify({ url: window.location.href, cookies: document.cookie, localStorage: JSON.stringify(localStorage), sessionStorage: JSON.stringify(sessionStorage), viewport: { width: window.innerWidth, height: window.innerHeight } })"`. Parse the single result into the 5 fields. Reduces latency from ~5x round-trip to ~1x. |
| Batch restore operations similarly | `restore_state()` makes N+M+K calls (one per localStorage key, sessionStorage key, and cookie). | Medium-High | Combine into 2-3 calls max: one for localStorage (iterate object in JS), one for sessionStorage, one for cookies. The JS function receives the full data object and restores everything in one evaluate call. This also eliminates the JS injection surface entirely. |

## Anti-Features

Things to deliberately NOT do in this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Add authentication to HTTP server | Localhost-only, single-user tool. Auth adds complexity without security benefit in the current deployment model. | Document the security model. Ensure binding to `127.0.0.1` specifically (not `localhost` which may resolve to `::1`). |
| Add comprehensive test coverage | Separate milestone. Mixing test writing with bug fixing bloats scope and slows delivery. | Track test gaps. Fix bugs cleanly so tests are easy to add later. |
| Database migration framework | Not needed until schema changes again. Current `CREATE TABLE IF NOT EXISTS` works for sole user. | Accept that schema changes require DB recreation for now. |
| Rate limiting / request throttling | Single-user local tool. No runaway client risk in practice. | Not needed. |
| Normalize console logs into separate table on write | The normalized `console_logs` table is rarely populated (logs go to `responses.console_logs` blob). Fixing the write path to also normalize is a larger change. | Fix the read path to parse the blob on demand. Normalization can be a future enhancement. |
| Refactor global state pattern in app.py | Module-level globals (`playwright_manager`, `database`, etc.) are ugly but work fine for a single-user server. Refactoring to dependency injection is an architectural change. | Leave as-is. Address when adding tests (different milestone). |
| Fix the asyncio lock serialization bottleneck | The single lock on PlaywrightManager is inherent to stdio-based subprocess communication. Cannot have concurrent requests over a single stdin/stdout pair. | Accept the limitation. The combined-evaluate changes reduce lock contention by reducing call count. |

## Feature Dependencies

```
Fix str(params) → json.dumps(params)           (independent)
Fix console_error_count                         (independent)
Fix console log level filtering                 (independent)
Add pydantic-settings dependency                (independent)
Pin @playwright/mcp version                     (independent)
Remove debug logging                            (independent)

Batch DB transactions                           (independent, but test after all DB-touching fixes)
  └── Should be done AFTER str(params) fix (both touch the proxy endpoint flow)

Combine capture_state evaluates                 (independent)
Fix JS injection in restore_state               → depends on understanding MCP evaluate schema
Batch restore_state operations                  → depends on JS injection fix (same code area)
  └── Combine capture + fix restore should be done together (same file, related patterns)
```

## MVP Recommendation

**Priority order for this milestone:**

1. **Low-hanging fruit first (all Low complexity, independent):**
   - `json.dumps(params)` fix
   - `pydantic-settings` dependency
   - Pin `@playwright/mcp` version
   - Remove debug logging
   - Fix `console_error_count`
   - Fix console log level filtering

2. **Then transaction batching:**
   - Add `transaction()` context manager to Database class
   - Wrap proxy endpoint DB operations in single transaction
   - Wrap snapshot cycle DB operations in single transaction

3. **Then evaluate consolidation (capture + restore together):**
   - Combine 5 capture_state calls into 1
   - Rewrite restore_state to use bulk JS functions (fixes injection + batches calls)

**Defer to future milestone:**
- Comprehensive test coverage (separate scope)
- Console log normalization on write path
- App-level architectural refactoring

## Complexity Budget

| Category | Item Count | Estimated Effort |
|----------|-----------|-----------------|
| Low complexity fixes | 6 | ~1-2 hours total |
| Medium complexity (transactions) | 1 | ~1-2 hours |
| Medium complexity (evaluate consolidation) | 2-3 | ~2-3 hours |
| **Total** | **~10 items** | **~5-7 hours** |

## Sources

- Direct codebase analysis: `operations.py`, `app.py`, `session_state.py`, `config.py`
- `.planning/codebase/CONCERNS.md` (tech debt audit from 2026-03-09)
- `.planning/PROJECT.md` (project requirements and scope)
- aiosqlite transaction behavior: Python sqlite3 module defaults to deferred transactions; aiosqlite wraps this transparently. Removing intermediate commits and committing once at context exit is the standard pattern. (MEDIUM confidence -- based on sqlite3/aiosqlite known behavior, not verified against current docs)
- Playwright MCP evaluate schema: The `browser_evaluate` tool accepts `function` as a string. Whether it supports a separate `arg` parameter for safe argument passing is unverified against the current MCP schema. (LOW confidence -- needs verification at implementation time)
