# Domain Pitfalls

**Domain:** Python async MCP proxy — dependency modernization and tech debt cleanup
**Researched:** 2026-03-09
**Overall confidence:** MEDIUM (web search unavailable; based on codebase analysis + training data)

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or broken production behavior.

### Pitfall 1: Transaction Batching Breaks Existing Error Recovery

**What goes wrong:** Wrapping `create_request` + `create_response` + `update_session_activity` in a single transaction means if the Playwright RPC fails mid-flow, the request record is also rolled back. Currently, requests are committed independently before the Playwright call (line 438 of `app.py`), so failed requests are still recorded in the database. Batching naively erases this audit trail.

**Why it happens:** The current per-operation commit pattern is wasteful (3+ commits per proxy call), so the instinct is to wrap everything in one transaction. But the current code commits the request *before* calling Playwright, which is intentional — it records what was attempted even if the downstream call fails.

**Consequences:** Lost observability. Failed requests vanish from the database. Debugging production issues becomes harder because there is no record of what was sent to Playwright.

**Prevention:**
- Batch only operations that share a success/failure boundary. The request record should commit independently (before) the Playwright call.
- Group post-RPC operations: `create_response` + `update_session_activity` + console log storage can share one transaction.
- For snapshot capture: `save_snapshot` + `update_session_state_from_snapshot` + `cleanup_old_snapshots` can share one transaction (all operate on the same session after a successful capture).
- Design the `transaction()` context manager so it is opt-in per call site, not a global behavior change.

**Detection:** After implementing transaction batching, verify that a failed Playwright RPC still produces a row in the `requests` table. Write a test that simulates a Playwright timeout and checks the database state.

**Phase:** Database transaction batching phase.

---

### Pitfall 2: MCP SDK Version Jump Breaking Server/Client Protocol

**What goes wrong:** The `mcp>=1.0.0` dependency is a floor pin with no ceiling. The MCP Python SDK has been evolving rapidly. A `pip install --upgrade` may pull a version that changes `Server` constructor signatures, `Tool` schema validation, or the stdio transport protocol. The codebase imports `mcp.server.Server`, `mcp.server.stdio.stdio_server`, and `mcp.types.TextContent`/`Tool` — all of which are surface-area targets for breaking changes.

**Why it happens:** The MCP ecosystem is young and fast-moving. The SDK does not yet have strong stability guarantees. The project pins `>=1.0.0` which allows any future major version.

**Consequences:** The MCP client (`mcp_server.py`) stops accepting connections from Claude Desktop or other MCP hosts. Silent protocol-level failures are possible — the tool may start but produce malformed JSON-RPC responses.

**Prevention:**
- Pin to a specific minor version range: `mcp>=1.0.0,<2.0.0` (or tighter, like `~=1.x.y` based on the current installed version).
- Before upgrading, check the MCP SDK changelog for breaking changes in `Server`, `stdio_server`, `Tool`, and `TextContent`.
- Test the full MCP handshake (initialize, tools/list, tools/call) after any SDK version bump, not just import success.

**Detection:** After upgrading, run `echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | uv run playwright-proxy-client` and verify the response lists all 9 tools with correct schemas.

**Phase:** Dependency update phase. Pin version ceiling before upgrading.

---

### Pitfall 3: Removing Debug Code That Masks a Schema Migration Bug

**What goes wrong:** The debug logging in `list_sessions()` (lines 121-156 of `operations.py`) iterates over every field and catches `KeyError`/`IndexError` individually. This was added to debug a schema mismatch — likely when Phase 7 added columns (`current_url`, `cookies`, etc.) to the `sessions` table. Removing this debug code is correct, but if the underlying schema issue resurfaces (e.g., running against a pre-Phase-7 database), the error will now be an opaque `KeyError` deep in the Session constructor instead of a clear "Missing field X in sessions table" log.

**Why it happens:** The debug code is wasteful (imports `logging` inside a loop, iterates every row field by field) but it also acts as a canary for a real problem: the project has no database migration system. `CREATE TABLE IF NOT EXISTS` does not add columns to existing tables.

**Consequences:** Users (including the sole developer) who have an old `proxy.db` from before Phase 7 will get silent crashes when `list_sessions()` or `get_latest_session_snapshot()` tries to access columns that do not exist.

**Prevention:**
- Remove the debug loops, but add a startup schema validation check. On `Database.connect()`, query `PRAGMA table_info(sessions)` and verify all expected columns exist.
- If columns are missing, `ALTER TABLE sessions ADD COLUMN ... DEFAULT NULL` at startup (idempotent migration).
- At minimum, add a clear error message: "Database schema outdated. Delete proxy.db and restart."

**Detection:** Before removing debug code, verify a clean database (created by current `schema.py`) has all columns that `list_sessions()` expects. Test by deleting `proxy.db` and restarting.

**Phase:** Debug code removal phase. Must pair with startup schema validation.

---

### Pitfall 4: JavaScript Injection Fix Changes Playwright MCP Evaluate Semantics

**What goes wrong:** The fix for JS injection in `session_state.py` (lines 198-239) is to switch from f-string interpolation (`f"() => localStorage.setItem('{key}', '{value_escaped}')"`) to Playwright's argument-passing pattern (`evaluate(function, arg)`). However, the Playwright MCP protocol's `browser_evaluate` tool may not support the `arg` parameter. The MCP tool schema defines a `function` string parameter — it may or may not accept additional arguments.

**Why it happens:** Playwright's native Node.js API supports `page.evaluate((arg) => ..., arg)`, but the MCP wrapper (`@playwright/mcp`) may only expose the function body as a string with no argument-passing mechanism. The assumption that MCP evaluate works identically to the native API is unverified.

**Consequences:** The "fix" breaks state restoration entirely. localStorage/sessionStorage/cookies stop being restored because the evaluate call rejects or ignores the argument parameter.

**Prevention:**
- Before implementing the fix, test whether `browser_evaluate` in the current Playwright MCP version accepts an `arg` or `arguments` parameter alongside `function`. Send a manual test RPC with an argument and check the response.
- If the MCP tool does not support arg passing, use `JSON.stringify()` + `JSON.parse()` within the function body as a safe escaping strategy: build one JS object containing all key-value pairs, JSON-serialize it with `json.dumps()`, and parse it inside the evaluate function. This eliminates direct string interpolation of user-controlled values.
- Example safe pattern without arg passing:
  ```python
  data_json = json.dumps(storage_data)  # Python handles escaping
  function = f"() => {{ Object.entries(JSON.parse({json.dumps(data_json)})).forEach(([k,v]) => localStorage.setItem(k,v)) }}"
  ```

**Detection:** After implementing, test state capture and restore round-trip with values containing single quotes, double quotes, backticks, `${}` template literals, newlines, and Unicode characters.

**Phase:** Security fix phase. Requires investigation of Playwright MCP evaluate tool schema first.

## Moderate Pitfalls

### Pitfall 5: Pydantic Settings Config Class Deprecation

**What goes wrong:** The `config.py` uses `class Config` inside the Settings model (line 80). Pydantic v2 deprecated the nested `Config` class in favor of `model_config = SettingsConfigDict(...)`. While `class Config` still works in current pydantic-settings, a future version may warn or break.

**Prevention:**
- When adding `pydantic-settings` to `pyproject.toml`, also migrate from `class Config` to:
  ```python
  model_config = SettingsConfigDict(
      env_prefix="PLAYWRIGHT_PROXY_",
      env_file=".env",
      env_file_encoding="utf-8",
  )
  ```
- This is a small change but should be done alongside the dependency fix to avoid accumulating more debt.

**Phase:** Dependency update phase. Do alongside adding `pydantic-settings` to dependencies.

---

### Pitfall 6: Console Log Parsing Assumes Consistent JSON Structure

**What goes wrong:** The fix for console log level filtering (line 669 of `app.py`) requires parsing the raw blob stored in `responses.console_logs`. But the blob format depends on what Playwright MCP returns for `browser_console_messages`, which is not a stable interface. The blob might be a JSON array of objects, newline-delimited text, or a structured MCP content block — the format is whatever Playwright MCP emitted, stored verbatim.

**Why it happens:** The codebase stores console logs as raw blobs specifically to avoid transformation issues ("No transformation on write"). But this means the reader must handle whatever format the upstream produces.

**Consequences:** The parser works for the format currently produced, then breaks silently on a Playwright MCP update that changes the format. Or it fails on edge cases: logs with non-UTF8 characters, logs with embedded JSON, very large log outputs.

**Prevention:**
- Before writing the parser, capture several real console log blobs from the database to understand the actual format. Do not assume a format from documentation.
- Write the parser defensively: try JSON parse first, fall back to line-by-line text parsing, and return unfiltered content if parsing fails (current behavior, but with a warning log).
- Add a test with real captured blob data, not fabricated test fixtures.

**Detection:** Run the proxy against a page with console output at multiple levels (`console.log`, `console.warn`, `console.error`), then inspect the raw `console_logs` column in SQLite to see the actual stored format.

**Phase:** Console log fix phase. Requires sample data collection first.

---

### Pitfall 7: `@playwright/mcp` Version Pin May Not Match Cached Version

**What goes wrong:** Changing `@playwright/mcp@latest` to `@playwright/mcp@0.0.18` (or whatever specific version) in config seems safe. But `npx` caches packages and may already have a different version cached. If the pinned version has different CLI flags, tool names, or response formats compared to what the developer has been running, the proxy breaks immediately on the version pin — not on the next upgrade.

**Why it happens:** The developer has been running `@latest` which auto-resolved to whatever was current. Pinning to a specific version is correct, but the pin must match what is actually working today.

**Prevention:**
- Before pinning, check what version is currently resolved: `npm view @playwright/mcp version` for the latest published version, and check `~/.npm/_npx/` cache for the locally cached version.
- Pin to the exact version that is currently working, verify everything works, then plan upgrades separately.
- Add a version detection step in `PlaywrightManager.start()` that logs the actual Playwright MCP version on startup.

**Detection:** After pinning, run the full proxy flow (create session, navigate, snapshot, get_content) to verify no regressions.

**Phase:** Dependency pinning phase.

---

### Pitfall 8: Combining 5 Evaluate RPCs Into 1 Changes Error Semantics

**What goes wrong:** Currently, if one of the 5 sequential `browser_evaluate` calls in `capture_state()` fails (e.g., cookies access denied on a cross-origin page), the others still succeed and partial state is captured. Combining them into a single evaluate call means one failure causes total state capture failure.

**Why it happens:** The combined JS function would be `() => ({ url: location.href, cookies: document.cookie, localStorage: JSON.stringify(localStorage), ... })`. If any property access throws, the entire function throws.

**Consequences:** A page that blocks `document.cookie` access (CORS, iframe sandbox) causes complete state capture failure instead of just missing cookies. The `session_snapshots` table gets no data at all instead of partial data.

**Prevention:**
- Wrap each property access in try/catch within the combined function:
  ```javascript
  () => ({
    url: (() => { try { return location.href } catch(e) { return null } })(),
    cookies: (() => { try { return document.cookie } catch(e) { return null } })(),
    localStorage: (() => { try { return JSON.stringify(localStorage) } catch(e) { return null } })(),
    sessionStorage: (() => { try { return JSON.stringify(sessionStorage) } catch(e) { return null } })(),
    viewport: (() => { try { return JSON.stringify({width: window.innerWidth, height: window.innerHeight}) } catch(e) { return null } })()
  })
  ```
- Handle `null` values in the Python-side parsing as "not available" rather than "not captured".
- Preserve the existing behavior where partial state is better than no state.

**Detection:** Test state capture on a page with restrictive CSP or cross-origin iframes.

**Phase:** Performance optimization phase (evaluate consolidation).

---

### Pitfall 9: aiosqlite Connection Lifecycle During Transaction Batching

**What goes wrong:** The `Database` class holds a single `aiosqlite.Connection` for its entire lifetime (set in `connect()`, cleared in `close()`). Adding a `transaction()` context manager that calls `BEGIN`/`COMMIT`/`ROLLBACK` works, but aiosqlite's `commit()` also implicitly starts a new transaction in autocommit mode. Mixing explicit transactions with the existing per-operation `commit()` calls can produce "cannot start a transaction within a transaction" errors if a batched operation calls a method that still has its own `commit()`.

**Why it happens:** The existing code calls `self.conn.commit()` after every write. A transaction context manager would wrap multiple writes without intermediate commits. But if any of those wrapped methods still call `commit()` internally, the transaction is committed prematurely.

**Prevention:**
- When adding a transaction context manager, add a flag (`self._in_transaction`) that causes individual method `commit()` calls to be skipped when inside a managed transaction.
- Alternatively, create transaction-aware variants of the methods (e.g., `_create_response_no_commit()`) used only within transactions.
- The simpler approach: remove individual `commit()` calls from all methods and always use explicit transaction management at the call site.

**Detection:** Write a test that wraps two writes in a transaction, forces an error on the second, and verifies the first was rolled back.

**Phase:** Database transaction batching phase.

## Minor Pitfalls

### Pitfall 10: `str(params)` to `json.dumps(params)` Changes Existing Data Format

**What goes wrong:** Fixing `str(request.params)` to `json.dumps(request.params)` on line 435 of `app.py` changes the storage format. Existing data in the database will have mixed formats — old rows with Python repr output (`{'url': 'https://example.com'}`), new rows with JSON (`{"url": "https://example.com"}`).

**Prevention:** This is a write-only field (CONCERNS.md confirms "Data is write-only"), so no existing code reads and parses it. The fix is safe. No migration of existing data is needed.

**Phase:** Tech debt cleanup phase. Low risk.

---

### Pitfall 11: FastAPI Lifespan Pattern Stability

**What goes wrong:** The codebase uses `@asynccontextmanager` for FastAPI lifespan. This is the current recommended pattern, but FastAPI evolves rapidly. A major version bump could deprecate it.

**Prevention:** Pin FastAPI to a compatible range: `fastapi>=0.115.0,<1.0.0`. The current lifespan pattern is stable and unlikely to change before 1.0.

**Phase:** Dependency update phase.

---

### Pitfall 12: pytest-asyncio Mode and Event Loop Changes

**What goes wrong:** The project uses `asyncio_mode = "auto"`. Upgrading pytest-asyncio may change how async fixtures are detected or how event loop scoping works, causing `RuntimeError: Event loop is closed` errors.

**Prevention:** Run the full test suite after upgrading pytest-asyncio, before making any code changes. Treat test failures from dependency upgrades as separate from code changes.

**Phase:** Dependency update phase.

---

### Pitfall 13: Ruff Version Gap Introduces New Violations

**What goes wrong:** Ruff evolves aggressively. Upgrading from 0.7 to a newer version may introduce new lint violations under the same rule codes (E, F, I, N, W) as rule implementations are refined.

**Prevention:** Run `ruff check .` after upgrading. Use `ruff check --fix .` for auto-fixable issues. Commit the Ruff upgrade separately from code changes so regressions are attributable.

**Phase:** Dependency update phase.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Dependency updates | MCP SDK breaking changes (#2) | Pin ceiling version, test full MCP handshake after upgrade |
| Dependency updates | pydantic-settings missing (#5) | Add to pyproject.toml, migrate Config class simultaneously |
| Dependency updates | pytest-asyncio event loop changes (#12) | Run tests before and after upgrade, pin range |
| Dependency updates | Ruff new violations (#13) | Run check after upgrade, fix in separate commit |
| Playwright version pin | Pinned version differs from cached (#7) | Check current running version first via npm/npx |
| Transaction batching | Request audit trail lost (#1) | Keep request commit separate from response commit |
| Transaction batching | aiosqlite commit/transaction conflict (#9) | Add in-transaction flag or remove per-method commits |
| Evaluate consolidation | Partial failure becomes total failure (#8) | Try/catch each property in combined JS function |
| JS injection fix | MCP evaluate may not support arg passing (#4) | Test against actual subprocess before implementing |
| Debug code removal | Schema mismatch resurfaces (#3) | Add startup schema validation or idempotent ALTER TABLE |
| Console log parsing | Unknown blob format (#6) | Inspect real stored data before writing parser |
| str() to json.dumps() | Mixed format in existing data (#10) | Safe — field is write-only, no code reads it |

## Sources

- Codebase analysis: `playwright_mcp_proxy/server/app.py`, `database/operations.py`, `server/session_state.py`, `server/playwright_manager.py`, `config.py`, `models/`
- `.planning/codebase/CONCERNS.md` — tech debt inventory with line-level references
- `.planning/PROJECT.md` — project scope, constraints, and key decisions
- Pydantic v2 migration patterns (training data, MEDIUM confidence)
- MCP SDK evolution (training data, LOW confidence — SDK is young and fast-moving)
- aiosqlite transaction semantics (training data, MEDIUM confidence)
- FastAPI lifespan patterns (training data, HIGH confidence — well-documented stable feature)

---

*Pitfalls audit: 2026-03-09*
