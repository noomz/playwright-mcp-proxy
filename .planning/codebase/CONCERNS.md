# Codebase Concerns

**Analysis Date:** 2026-03-09

## Tech Debt

**Unimplemented TODO: Console Error Counting:**
- Issue: `console_error_count` in proxy response metadata is always hardcoded to `0`
- Files: `playwright_mcp_proxy/server/app.py` (line 485)
- Impact: Clients cannot rely on `console_error_count` in `ResponseMetadata` to detect errors without fetching full console logs. The `get_console_error_count()` method exists in the database layer but is never called from the proxy endpoint.
- Fix approach: After storing the response, call `database.get_console_error_count(ref_id)` or parse console logs inline. Note: console logs are currently stored as a raw blob in `responses.console_logs`, not always parsed into the normalized `console_logs` table, so the DB method may return 0 anyway.

**Unimplemented TODO: Console Log Level Filtering:**
- Issue: Console log level filtering in `/console/{ref_id}` falls back to returning raw blob without parsing when no normalized logs exist
- Files: `playwright_mcp_proxy/server/app.py` (line 669)
- Impact: The `level` query parameter is silently ignored when logs are stored only as the raw blob (the common case), returning all logs regardless of filter. Users get misleading results.
- Fix approach: Parse the JSON blob in the fallback path and filter by level before returning.

**Debug Logging Left in Production Code:**
- Issue: `list_sessions()` and `get_latest_session_snapshot()` contain verbose field-by-field debug iteration with inline `import logging` statements
- Files: `playwright_mcp_proxy/database/operations.py` (lines 121-156, 401-429)
- Impact: Performance overhead on every row read. Redundant `import logging` inside loops. This was clearly added to debug a specific issue and should be removed.
- Fix approach: Remove the field-access debug loops. Keep the Session/SessionSnapshot construction directly. If schema mismatch errors recur, handle with a proper migration check at startup.

**Missing Dependency in pyproject.toml:**
- Issue: `pydantic-settings` is imported (`from pydantic_settings import BaseSettings`) but not listed in `[project.dependencies]`
- Files: `playwright_mcp_proxy/config.py` (line 7), `pyproject.toml`
- Impact: Fresh installs may fail if `pydantic-settings` is not transitively pulled in. Currently works because `pydantic` may pull it in, but this is not guaranteed.
- Fix approach: Add `pydantic-settings>=2.0.0` to `[project.dependencies]` in `pyproject.toml`.

**Params Stored as str() Not JSON:**
- Issue: Request params are stored via `str(request.params)` which produces Python repr format, not valid JSON
- Files: `playwright_mcp_proxy/server/app.py` (line 435)
- Impact: Stored params cannot be reliably deserialized. `str({'url': 'https://example.com'})` produces single-quoted Python dict notation, not JSON. Data is write-only.
- Fix approach: Use `json.dumps(request.params)` instead of `str(request.params)`.

## Security Considerations

**No Authentication on HTTP Server:**
- Risk: The FastAPI server at port 34501 has zero authentication. Any process on the machine (or network, if bound to 0.0.0.0) can create sessions, proxy browser commands, and read all stored data.
- Files: `playwright_mcp_proxy/server/app.py` (entire file), `playwright_mcp_proxy/config.py` (line 14: default host is `localhost`)
- Current mitigation: Default bind to `localhost` limits exposure to local processes only. No network-level risk by default.
- Recommendations: Add a shared secret / API key header for inter-component auth. Consider binding exclusively to `127.0.0.1` (not `localhost` which may resolve to IPv6). Document the security model clearly for users who change `server_host`.

**JavaScript Injection in Session Restoration:**
- Risk: `restore_state()` interpolates user-controlled data directly into JavaScript strings via f-strings, enabling code injection
- Files: `playwright_mcp_proxy/server/session_state.py` (lines 198-223, 230-239)
- Current mitigation: Data originates from previously captured browser state (self-generated), not direct user input. The escape logic (line 198) only handles `\\` and `'`, missing other injection vectors like backticks, `${}`, or newlines.
- Recommendations: Pass data as arguments to the evaluate function rather than interpolating into the function body. Use Playwright's built-in `evaluate(function, arg)` pattern if the MCP protocol supports it.

**Cookie Capture Limitation:**
- Risk: `document.cookie` cannot access HttpOnly cookies, which are the most security-sensitive cookies (session tokens, CSRF tokens)
- Files: `playwright_mcp_proxy/server/session_state.py` (lines 60-69)
- Current mitigation: None. This is a fundamental limitation acknowledged in comments (line 59).
- Recommendations: Use Playwright's context-level cookie API (`context.cookies()`) if the MCP protocol exposes it. Document this limitation.

## Performance Bottlenecks

**Per-Operation Database Commits:**
- Problem: Every single database write calls `await self.conn.commit()` individually
- Files: `playwright_mcp_proxy/database/operations.py` (lines 68, 98, 106, 176, 214, 251, 268, 342, 347, 376, 493, 528)
- Cause: Each proxy request triggers 3+ separate commits (create_request, create_response, update_session_activity). The periodic snapshot task adds more (save_snapshot, update_session_state_from_snapshot, cleanup_old_snapshots = 3 commits per session per interval).
- Improvement path: Batch related operations into a single transaction. Add a `transaction()` context manager to the Database class. For the proxy endpoint, wrap the request+response+activity update in one commit.

**Snapshot Capture Makes 5 Sequential RPCs:**
- Problem: `capture_state()` makes 5 sequential `browser_evaluate` calls to the Playwright subprocess, each waiting for a round-trip
- Files: `playwright_mcp_proxy/server/session_state.py` (lines 44-108)
- Cause: Each state piece (URL, cookies, localStorage, sessionStorage, viewport) is a separate RPC call through the subprocess stdio pipe, serialized by the asyncio lock in `PlaywrightManager`.
- Improvement path: Combine all 5 evaluations into a single `browser_evaluate` call that returns a JSON object with all state. This reduces 5 RPCs to 1.

**Single Asyncio Lock for All Playwright Requests:**
- Problem: `PlaywrightManager._lock` serializes ALL requests to the Playwright subprocess, including health checks
- Files: `playwright_mcp_proxy/server/playwright_manager.py` (line 27, 155)
- Cause: Stdio pipe communication is inherently sequential (one request, one response), so the lock is necessary for correctness. But health check pings contend with user requests.
- Improvement path: This is an inherent limitation of stdio-based subprocess communication. Consider separating health check logic from the request lock, or using a separate mechanism (process.poll() instead of tools/list ping).

## Fragile Areas

**Single Active Session per MCP Client:**
- Files: `playwright_mcp_proxy/client/mcp_server.py` (line 19: `current_session_id`)
- Why fragile: The MCP client uses a single global `current_session_id`. Creating a new session silently abandons the previous one without closing it. The abandoned session stays "active" in the database forever, triggering orphan detection on restart.
- Safe modification: Any changes to session management must account for the global variable pattern.
- Test coverage: No tests exist for the MCP client layer at all.

**Global State in Server App:**
- Files: `playwright_mcp_proxy/server/app.py` (lines 29-33)
- Why fragile: `playwright_manager`, `database`, `session_state_manager`, and `snapshot_task` are module-level globals set during lifespan. Any import-time access or test that doesn't go through `lifespan()` will hit uninitialized globals.
- Safe modification: All endpoint handlers depend on these globals. Testing the app requires either the full lifespan context or monkey-patching globals.
- Test coverage: No integration tests for the HTTP endpoints exist. Only database and unit tests.

**Subprocess Stdio Protocol Assumptions:**
- Files: `playwright_mcp_proxy/server/playwright_manager.py` (lines 164-184)
- Why fragile: Assumes Playwright MCP subprocess returns exactly one JSON line per request. If the subprocess emits any unexpected output (warnings, debug info) to stdout, the JSON parser will fail and the response will be lost. The chunked reader handles large lines but not multi-line or interleaved output.
- Safe modification: Any upstream Playwright MCP version change could alter output format.
- Test coverage: No tests for PlaywrightManager.

**Health Check Can Trigger Recursive Restart:**
- Files: `playwright_mcp_proxy/server/playwright_manager.py` (lines 244-280)
- Why fragile: `_attempt_restart()` calls `self.stop()` which cancels `_health_check_task`, then `self.start()` which creates a new `_health_check_task`. But `_attempt_restart` is called FROM the health check task. The `CancelledError` handling in the health check loop (line 239) should catch this, but the flow is subtle and easy to break.
- Safe modification: Ensure any restart logic changes account for the self-referential cancellation pattern.
- Test coverage: No tests for restart logic.

## Scaling Limits

**SQLite Single Writer:**
- Current capacity: Single concurrent writer, suitable for single-user local tool use
- Limit: SQLite's write lock means concurrent proxy requests queue at the database layer. With per-operation commits, this creates significant contention under load.
- Scaling path: Batch commits, WAL mode (not currently enabled), or migrate to PostgreSQL for multi-user scenarios.

**Single Playwright Subprocess:**
- Current capacity: One browser instance, one page context
- Limit: All sessions share the same Playwright subprocess. The MCP protocol appears to manage a single browser context, so multiple sessions may interfere with each other at the browser level (shared cookies, shared navigation state).
- Scaling path: Spawn separate Playwright subprocess per session. Requires significant architecture changes.

**Unbounded Data Growth:**
- Current capacity: All requests, responses, and snapshots accumulate indefinitely
- Limit: The `responses` table stores full page snapshots as TEXT blobs. Heavy usage accumulates data without any cleanup mechanism (except snapshot rotation). No TTL, no archiving, no pruning of old sessions/responses.
- Scaling path: Add cleanup for old sessions and their associated requests/responses. Add `VACUUM` scheduling or database size monitoring.

## Dependencies at Risk

**`@playwright/mcp@latest` via npx:**
- Risk: The subprocess command uses `@latest` tag, meaning any npm publish of `@playwright/mcp` changes the runtime behavior without warning. A breaking change in the MCP protocol, tool names, or response format could silently break the proxy.
- Files: `playwright_mcp_proxy/config.py` (line 29: `default=["@playwright/mcp@latest"]`)
- Impact: Complete system failure if Playwright MCP changes its stdio protocol, tool names, or response structure.
- Migration plan: Pin to a specific version (e.g., `@playwright/mcp@0.0.18`). Add version detection during initialization.

## Missing Critical Features

**No Session Cleanup / Close Flow:**
- Problem: There is no way to explicitly close a session and clean up its data. The `browser_close` tool is proxied but does not update session state. Abandoned sessions remain "active" until server restart triggers orphan detection.
- Files: `playwright_mcp_proxy/client/mcp_server.py` (tool list), `playwright_mcp_proxy/server/app.py` (no close endpoint)
- Blocks: Proper resource management, multi-session workflows.

**No Database Migration Strategy:**
- Problem: Schema changes rely on `CREATE TABLE IF NOT EXISTS`. Adding columns to existing tables requires manual migration or database recreation. The Phase 7 schema changes (new columns on `sessions`, new `session_snapshots` table) would fail on an existing database that already has a `sessions` table without those columns.
- Files: `playwright_mcp_proxy/database/schema.py`
- Blocks: Safe upgrades for users with existing databases.

**No Rate Limiting or Request Throttling:**
- Problem: No limits on request frequency to the Playwright subprocess or HTTP server.
- Blocks: Protection against runaway clients flooding the subprocess.

## Test Coverage Gaps

**MCP Client Layer - Zero Tests:**
- What's not tested: The entire `client/mcp_server.py` module including tool routing, HTTP client interaction, session management, and error handling
- Files: `playwright_mcp_proxy/client/mcp_server.py`
- Risk: The client is the primary user-facing interface. Changes to tool handling, response formatting, or error paths are completely untested.
- Priority: High

**HTTP Endpoint Integration Tests - Zero Tests:**
- What's not tested: FastAPI endpoint behavior including request validation, response formatting, error codes, the full proxy flow, diff behavior via HTTP, and the content search/context-lines feature
- Files: `playwright_mcp_proxy/server/app.py`
- Risk: All endpoint logic (proxy flow, diff logic, search filtering) is only tested indirectly via database unit tests. The actual HTTP request/response cycle is untested.
- Priority: High

**PlaywrightManager - Zero Tests:**
- What's not tested: Subprocess spawning, health check loop, restart logic, JSON-RPC communication, chunked line reading, stderr monitoring
- Files: `playwright_mcp_proxy/server/playwright_manager.py`
- Risk: The most complex and failure-prone component (subprocess lifecycle, exponential backoff, stdio parsing) has no test coverage. The chunked reader for large responses is completely untested.
- Priority: High

**SessionStateManager - Partial Coverage:**
- What's not tested: Integration with real Playwright subprocess, actual browser state capture/restore. Only unit tests with mocks exist.
- Files: `playwright_mcp_proxy/server/session_state.py`, `tests/test_phase7_state_capture.py`
- Risk: Mocks may not accurately represent Playwright MCP response format. The JavaScript injection concern in `restore_state()` is not tested with adversarial inputs.
- Priority: Medium

**Search/Context Lines Feature - Zero Tests:**
- What's not tested: The `search_for`, `before_lines`, and `after_lines` parameters on `/content/{ref_id}` endpoint
- Files: `playwright_mcp_proxy/server/app.py` (lines 556-589)
- Risk: This grep-like filtering logic with gap separators has edge cases (overlapping context windows, empty matches, search at beginning/end of content) that are completely untested.
- Priority: Medium

**Orphan Detection Integration - Partial Coverage:**
- What's not tested: The `detect_orphaned_sessions()` function itself. Tests in `test_phase7_startup_detection.py` manually replicate the detection logic rather than calling the actual function.
- Files: `playwright_mcp_proxy/server/app.py` (lines 48-138), `tests/test_phase7_startup_detection.py`
- Risk: If the detection logic in `app.py` diverges from what the tests validate, bugs will not be caught.
- Priority: Low

---

*Concerns audit: 2026-03-09*
