# Architecture Patterns

**Domain:** Python MCP proxy tech debt fixes
**Researched:** 2026-03-09

## Current Architecture (Unchanged by Fixes)

The two-component architecture (MCP Client + HTTP Server) remains intact. All four proposed fixes live entirely within the **HTTP Server component** and its sub-layers. No changes to the MCP Client, no new components, no new inter-component communication.

```
MCP Client (stdio) --HTTP--> HTTP Server --stdio--> Playwright subprocess
                                  |
                              Database (SQLite)
```

The fixes touch three internal boundaries within the HTTP Server:

```
app.py (endpoint handlers)
   |
   +-- Database (operations.py)      <-- Fix 1: transaction context manager
   |                                  <-- Fix 4: console error counting
   |
   +-- SessionStateManager            <-- Fix 2: single evaluate call
       (session_state.py)             <-- Fix 3: safe arg passing
           |
           +-- PlaywrightManager      (no changes, send_request interface stable)
               (playwright_manager.py)
```

## Component Boundaries

| Component | Responsibility | Changes in This Milestone |
|-----------|---------------|---------------------------|
| `Database` (operations.py) | Async SQLite CRUD wrapper | Add `transaction()` context manager; add inline error counting helper |
| `SessionStateManager` (session_state.py) | Browser state capture/restore via evaluate | Merge 5 RPCs into 1; use arg passing for restore |
| `app.py` (endpoint handlers) | Request routing, response building | Wire console_error_count; use transactions in proxy flow |
| `PlaywrightManager` (playwright_manager.py) | Subprocess lifecycle, JSON-RPC | **No changes** -- stable interface |
| `MCP Client` (mcp_server.py) | Tool definitions, stdio protocol | **No changes** |
| Models (api.py, database.py) | Data shapes | **No changes** |

## Recommended Architecture Changes

### Fix 1: Transaction Context Manager on Database

**What:** Add an async context manager that defers `commit()` until the block exits, rolling back on exception.

**Where:** `playwright_mcp_proxy/database/operations.py` -- new method on `Database` class.

**Pattern:**

```python
from contextlib import asynccontextmanager

class Database:
    @asynccontextmanager
    async def transaction(self):
        """Batch multiple operations into a single transaction.

        Usage:
            async with database.transaction():
                await database.create_request(req)
                await database.create_response(resp)
                await database.update_session_activity(session_id)
            # Single commit happens here
        """
        try:
            yield
            await self.conn.commit()
        except Exception:
            await self.conn.rollback()
            raise
```

**Constraint:** Individual operation methods currently call `await self.conn.commit()` after every write. Two approaches:

1. **Recommended:** Split each write method into a "no-commit" variant (private) and a "commit" variant (public). The transaction context manager calls no-commit variants. This avoids breaking existing callers.

2. **Alternative:** Remove `commit()` from all methods, require callers to always use `transaction()`. Simpler but changes every call site at once.

**Approach 1 is safer** because it allows incremental adoption. Wrap the proxy endpoint flow first (create_request + create_response + update_session_activity = 3 commits reduced to 1), then tackle periodic_snapshot_task (save_snapshot + update_session_state_from_snapshot + cleanup_old_snapshots = 3 commits reduced to 1).

**Implementation detail:** aiosqlite uses autocommit=off by default (SQLite's `isolation_level` is `""` which means deferred transactions). Each `execute()` that modifies data starts an implicit transaction if one isn't active. The explicit `commit()` ends it. So removing intermediate `commit()` calls within a `transaction()` block naturally batches into one transaction -- no special SQLite configuration needed.

**Data flow change:** None. Same data, same tables, fewer fsync calls.

### Fix 2: Single Evaluate Call for State Capture

**What:** Replace 5 sequential `browser_evaluate` RPCs in `capture_state()` with one combined call that returns all state as a JSON object.

**Where:** `playwright_mcp_proxy/server/session_state.py` -- `capture_state()` method.

**Current flow (5 RPCs, 5 lock acquisitions):**
```
capture_state() -> send_request("browser_evaluate", url_fn)      -> parse
                -> send_request("browser_evaluate", cookies_fn)   -> parse
                -> send_request("browser_evaluate", ls_fn)        -> parse
                -> send_request("browser_evaluate", ss_fn)        -> parse
                -> send_request("browser_evaluate", viewport_fn)  -> parse
```

**New flow (1 RPC, 1 lock acquisition):**
```
capture_state() -> send_request("browser_evaluate", combined_fn) -> parse all fields
```

**Combined function:**
```javascript
() => JSON.stringify({
    url: window.location.href,
    cookies: document.cookie,
    localStorage: JSON.stringify(localStorage),
    sessionStorage: JSON.stringify(sessionStorage),
    viewport: { width: window.innerWidth, height: window.innerHeight }
})
```

**Key consideration:** The combined function returns a JSON string. `_extract_evaluate_result()` returns a string, so the caller must `json.loads()` the result to get individual fields. The existing `_parse_cookie_string()` helper still applies to the cookies field.

**Component boundary preserved:** `SessionStateManager` still calls `PlaywrightManager.send_request()` with the same interface. No changes to PlaywrightManager.

**Risk:** If any single evaluation (e.g., sessionStorage on a cross-origin page) throws, the entire combined call fails instead of just that piece. Add a try/catch within the JS function:

```javascript
() => {
    const state = { url: '', cookies: '', localStorage: '{}', sessionStorage: '{}', viewport: '{}' };
    try { state.url = window.location.href; } catch(e) {}
    try { state.cookies = document.cookie; } catch(e) {}
    try { state.localStorage = JSON.stringify(localStorage); } catch(e) {}
    try { state.sessionStorage = JSON.stringify(sessionStorage); } catch(e) {}
    try { state.viewport = JSON.stringify({width: window.innerWidth, height: window.innerHeight}); } catch(e) {}
    return JSON.stringify(state);
}
```

### Fix 3: Safe Arg Passing for Playwright Evaluate

**What:** Replace f-string interpolation of user data into JavaScript function bodies with argument passing.

**Where:** `playwright_mcp_proxy/server/session_state.py` -- `restore_state()` method.

**Current vulnerable pattern (lines 198-207):**
```python
value_escaped = value.replace("\\", "\\\\").replace("'", "\\'")
await self.playwright.send_request("tools/call", {
    "name": "browser_evaluate",
    "arguments": {
        "function": f"() => localStorage.setItem('{key}', '{value_escaped}')",
    },
})
```

**The problem:** The escape logic misses backticks, `${}` template literals, newlines, and null bytes. A stored value like `` '); window.location='http://evil.com';// `` (with a crafted escape bypass) could execute arbitrary JS.

**Solution approach -- combine into single evaluate with JSON data:**

Since Playwright MCP's `browser_evaluate` tool accepts a `function` string parameter but likely does NOT support a separate `arg` parameter (the MCP tool wraps Playwright's `page.evaluate()` but the MCP protocol schema only exposes `function` as a string), the safest pattern is to embed the data as a JSON string literal inside the function, parsed at runtime:

```python
import json

async def restore_state(self, snapshot: SessionSnapshot) -> bool:
    # Build the complete state restoration as a single evaluate call
    state_data = {}
    if snapshot.local_storage:
        state_data["localStorage"] = json.loads(snapshot.local_storage)
    if snapshot.session_storage:
        state_data["sessionStorage"] = json.loads(snapshot.session_storage)
    if snapshot.cookies:
        state_data["cookies"] = json.loads(snapshot.cookies)

    # json.dumps produces a safely escaped JSON string
    # No user data is interpolated as JavaScript code
    state_json = json.dumps(state_data)

    restore_fn = f"""(function() {{
        const state = JSON.parse({json.dumps(state_json)});
        if (state.localStorage) {{
            Object.entries(state.localStorage).forEach(([k, v]) =>
                localStorage.setItem(k, v));
        }}
        if (state.sessionStorage) {{
            Object.entries(state.sessionStorage).forEach(([k, v]) =>
                sessionStorage.setItem(k, v));
        }}
        if (state.cookies) {{
            state.cookies.forEach(c =>
                document.cookie = c.name + '=' + c.value);
        }}
    }})()"""
```

**Why `json.dumps(json.dumps(...))` is safe:** The inner `json.dumps` serializes the Python dict to a JSON string. The outer `json.dumps` wraps it in quotes and escapes any special characters (backslashes, quotes, control characters) for embedding as a JavaScript string literal. `JSON.parse()` on the JS side reverses this. No user data ever appears as executable JavaScript syntax.

**Bonus:** This also collapses the per-key-value restore loops (N RPCs per storage type) into a single RPC, which is a significant performance improvement for sessions with many storage entries.

**Confidence on MCP evaluate arg support:** LOW. I could not verify whether Playwright MCP's `browser_evaluate` tool accepts an `arg` parameter alongside `function`. The codebase only uses `function` as the parameter. The JSON-embedding approach works regardless of whether arg passing is supported.

### Fix 4: Console Error Counting -- App Layer vs Database Layer

**What:** Replace the hardcoded `console_error_count=0` in the proxy endpoint with actual error counting.

**Where the count is consumed:** `playwright_mcp_proxy/server/app.py` line 485, in `ResponseMetadata` construction.

**Where counting could happen:**

| Location | Approach | Pros | Cons |
|----------|----------|------|------|
| Database layer (existing `get_console_error_count()`) | Query `console_logs` table after storing | Clean separation; method already exists | Console logs are rarely stored in normalized table; usually only in `responses.console_logs` blob |
| App layer (inline parse) | Parse `console_logs_data` JSON blob inline before building metadata | Works with the actual data flow; no extra DB query | Parsing logic in endpoint handler |
| **App layer (helper function)** | Extract parsing into a standalone function in app.py or a utils module | Testable; works with blob data; no DB round-trip | Minor code addition |

**Recommendation: App layer helper function.** The data is already in memory as `console_logs_data` (the raw blob from Playwright). Parse it there, count errors, avoid an extra DB query that would return 0 anyway (since normalized `console_logs` table is rarely populated).

```python
def count_console_errors(console_logs_data: Optional[str]) -> int:
    """Count error-level entries in console logs blob."""
    if not console_logs_data:
        return 0
    try:
        # Playwright MCP returns console logs as text with [ERROR] prefixes
        # or as JSON array -- handle both formats
        lines = console_logs_data.split('\n')
        return sum(1 for line in lines if '[error]' in line.lower() or '[ERROR]' in line)
    except Exception:
        return 0
```

**Note:** The exact format of console logs from Playwright MCP needs verification at implementation time. The function should handle whatever format the `browser_console_messages` tool returns. If it is JSON, parse as JSON and filter by level field.

**This fix also relates to the console log level filtering TODO** (line 669 in app.py). The same parsing logic can be reused in the `/console/{ref_id}` endpoint fallback path.

## Data Flow Changes

### Before (Proxy Endpoint)

```
POST /proxy
  1. get_session()                          -- read
  2. create_request()        -> COMMIT      -- write 1
  3. update_session_activity() -> COMMIT    -- write 2
  4. send_request() to Playwright           -- RPC
  5. create_response()       -> COMMIT      -- write 3
  6. Build ResponseMetadata(console_error_count=0)  -- hardcoded
  7. Return ProxyResponse
```

### After (Proxy Endpoint)

```
POST /proxy
  1. get_session()                          -- read
  2. send_request() to Playwright           -- RPC (moved before writes)
  3. count_console_errors(console_logs)     -- in-memory parse
  4. async with database.transaction():
       create_request()                     -- write (no commit)
       create_response()                    -- write (no commit)
       update_session_activity()            -- write (no commit)
                                            -- SINGLE COMMIT
  5. Build ResponseMetadata(console_error_count=N)
  6. Return ProxyResponse
```

**Key change:** Moving the Playwright RPC before the DB writes means we only write to the DB once we have the full response. If the RPC fails, we still need to write the error response, so the error path also uses a transaction.

### Before (Periodic Snapshot, per session)

```
capture_state()                    -- 5 RPCs, 5 lock acquisitions
save_session_snapshot()  -> COMMIT
update_session_state_from_snapshot() -> COMMIT
cleanup_old_snapshots()  -> COMMIT
```

### After (Periodic Snapshot, per session)

```
capture_state()                    -- 1 RPC, 1 lock acquisition
async with database.transaction():
    save_session_snapshot()        -- write (no commit)
    update_session_state_from_snapshot() -- write (no commit)
    cleanup_old_snapshots()        -- write (no commit)
                                   -- SINGLE COMMIT
```

## Suggested Build Order

The fixes have the following dependency structure:

```
Fix 1 (transaction ctx mgr)  <-- independent, foundational
Fix 4 (console error count)  <-- independent, trivial
Fix 3 (safe arg passing)     <-- independent, security-critical
Fix 2 (single evaluate)      <-- depends loosely on Fix 3 pattern knowledge
```

**Recommended order:**

1. **Fix 1: Transaction context manager** -- Foundational. Other fixes benefit from it (proxy endpoint flow, snapshot flow). Pure database layer change, easy to test in isolation with existing test fixtures.

2. **Fix 4: Console error counting** -- Trivial. Add a helper function, wire it into the proxy endpoint. Can immediately use the transaction from Fix 1 in the proxy flow refactor.

3. **Fix 3: Safe arg passing in restore_state()** -- Security fix. The JSON-embedding pattern established here informs Fix 2's approach. Changes only `restore_state()` in session_state.py.

4. **Fix 2: Single evaluate for capture_state()** -- Performance fix. Uses similar JS patterns to Fix 3. Changes only `capture_state()` in session_state.py. Can wrap the snapshot DB writes in Fix 1's transaction.

**Rationale for this order:**
- Fix 1 first because Fixes 2 and 4 both involve modifying the proxy/snapshot flows, and having transactions available means those modifications naturally incorporate batching.
- Fix 4 before Fix 3 because it is trivial and lets you ship a quick win.
- Fix 3 before Fix 2 because the safe JS data-embedding pattern used in restore informs the defensive try/catch pattern used in capture.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Making Database Methods Transaction-Aware via Flag
**What:** Adding `commit=True` parameter to every write method.
**Why bad:** Leaks transaction control into every method signature. Callers must remember to pass `commit=False` inside transactions. Easy to forget, leads to partial commits.
**Instead:** Use the context manager approach. Methods inside a `transaction()` block simply skip their own commit (context manager handles it). Methods outside still auto-commit.

### Anti-Pattern 2: Concatenating User Data into JS via String Escaping
**What:** Adding more escape sequences to the existing `replace()` chain.
**Why bad:** Escape-based sanitization is an endless arms race. There is always another character or encoding trick. The existing code already misses backticks, template literals, and control characters.
**Instead:** Use the `json.dumps(json.dumps(...))` + `JSON.parse()` pattern. Data is never interpreted as code.

### Anti-Pattern 3: Counting Errors via Separate DB Query
**What:** Calling `database.get_console_error_count(ref_id)` after `create_response()`.
**Why bad:** The normalized `console_logs` table is rarely populated (logs are stored as blobs in `responses.console_logs`). The query would return 0, which is the current broken behavior. Also adds an unnecessary DB round-trip.
**Instead:** Parse the in-memory blob before building the response metadata.

## Scalability Considerations

These fixes are local optimizations, not architectural changes. They matter for:

| Concern | Current Impact | After Fixes |
|---------|---------------|-------------|
| DB write contention | 3+ commits per proxy request, 3 per snapshot per session | 1 commit per proxy request, 1 per snapshot per session |
| Subprocess lock contention | 5 lock acquisitions per snapshot capture | 1 lock acquisition per snapshot capture |
| JS injection surface | Open via f-string interpolation | Closed via JSON data embedding |
| Console error visibility | Zero (hardcoded) | Accurate count from blob parsing |

None of these fixes change the single-writer SQLite constraint or the single-subprocess architecture. Those are out of scope per PROJECT.md.

## Sources

- Codebase analysis: `playwright_mcp_proxy/database/operations.py` (12 individual `commit()` calls identified)
- Codebase analysis: `playwright_mcp_proxy/server/session_state.py` (5 sequential RPCs in `capture_state()`, f-string interpolation in `restore_state()`)
- Codebase analysis: `playwright_mcp_proxy/server/app.py` (hardcoded `console_error_count=0` at line 485)
- aiosqlite documentation: SQLite isolation behavior with deferred transactions (HIGH confidence from training data -- aiosqlite wraps sqlite3 module which defaults to `isolation_level=""` meaning deferred transactions)
- Playwright MCP `browser_evaluate` arg support: LOW confidence -- could not verify via external sources; JSON-embedding approach works regardless

---

*Architecture research: 2026-03-09*
