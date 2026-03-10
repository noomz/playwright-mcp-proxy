---
phase: 04-evaluate-consolidation-security
plan: 01
subsystem: session-state
tags: [python, json, browser-evaluate, session-state, security, performance]

requires:
  - phase: 03-transaction-batching
    provides: Database operations and transaction batching used in server layer

provides:
  - 1-RPC combined capture_state() using single browser_evaluate with per-property try/catch
  - json.dumps()-based injection-safe restore_state() with no f-string user-data interpolation

affects:
  - Future session resumption work touching session_state.py

tech-stack:
  added: []
  patterns:
    - Combined JS evaluation: all capture properties in one browser_evaluate call with per-property try/catch
    - json.dumps embedding: all user-controlled data passed to JS via json.dumps() not f-string interpolation

key-files:
  created: []
  modified:
    - playwright_mcp_proxy/server/session_state.py
    - tests/test_phase7_state_capture.py

key-decisions:
  - "capture_state() now issues exactly 1 browser_evaluate RPC (was 5) using combined JS with per-property try/catch for graceful partial failure"
  - "restore_state() uses json.dumps() for all user data embedded in JS strings, eliminating manual .replace() escaping"
  - "Partial capture failure (null from JS try/catch) treated as fallback: None -> '{}' for storage, '' for url/cookies"
  - "Test assertion for injection safety: checks that setItem args are double-quoted (json.dumps output) not single-quoted (f-string)"

patterns-established:
  - "JSON embedding: embed user data in JS function strings via json.dumps(key) and json.dumps(value), never f-string interpolation"
  - "Combined JS evaluation: bundle multiple browser reads into one function returning a dict, with per-property try/catch"

requirements-completed: [PERF-02, SECR-01]

duration: 2min
completed: 2026-03-10
---

# Phase 4 Plan 01: Consolidate Capture RPCs and Injection-Safe Restore Summary

**Single-RPC browser state capture with per-property try/catch plus json.dumps()-based injection-safe restore eliminating all f-string user-data interpolation**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-10T08:09:12Z
- **Completed:** 2026-03-10T08:11:43Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- Replaced 5 sequential `browser_evaluate` RPCs in `capture_state()` with a single combined call, an 80% reduction in RPC overhead per capture operation
- Combined JS function wraps each property (url, cookies, localStorage, sessionStorage, viewport) in its own try/catch so a SecurityError on one property does not prevent the others
- Replaced all f-string interpolation in `restore_state()` with `json.dumps()` for keys, values, and cookie strings, closing the JS injection surface for user-controlled data containing quotes, backslashes, or newlines
- Added 3 new tests: `test_capture_state_partial_failure`, `test_restore_state_injection_safety`, `test_restore_state_special_chars`
- Updated 2 existing capture tests to use combined-mock pattern and assert `call_count == 1`
- Full test suite: 47 tests pass, zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Write failing tests for combined capture and injection-safe restore** - `70ce2b5` (test)
2. **Task 2: Implement combined capture and injection-safe restore** - `9d89fcc` (feat)

**Plan metadata:** _(docs commit follows)_

_Note: TDD tasks have two commits: failing tests (RED) then implementation (GREEN)_

## Files Created/Modified

- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/playwright_mcp_proxy/server/session_state.py` - capture_state() consolidated to 1 RPC with combined JS; restore_state() uses json.dumps() throughout
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/tests/test_phase7_state_capture.py` - 7 existing tests updated + 3 new tests for partial failure, injection safety, special characters

## Decisions Made

- **Combined JS with try/catch per property:** A single `browser_evaluate` returning a dict eliminates 4 round-trips. Per-property try/catch in JS means a SecurityError on localStorage does not abort capture of the other 4 properties — graceful degradation.
- **null from JS → Python fallback:** When a JS try/catch catches an error it returns the fallback value from JS (`"{}"` for storage, `""` for cookies). When JS returns null at the JSON level (via `null` literal from `None` serialization in test), Python normalises to `"{}"` / `""`. Both cases handled.
- **json.dumps for all JS embedding:** `json.dumps(key)` and `json.dumps(value)` always produce double-quoted, properly escaped JSON literals. Removes need for manual `.replace("\\", "\\\\").replace("'", "\\'")` which was incomplete (missed newlines, Unicode escapes, etc.).
- **Injection safety test strategy:** Checking that the character immediately after `setItem(` is `"` (json.dumps double-quote) rather than `'` (old f-string single-quote) is the clearest mechanical proof of the pattern.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion for injection safety corrected**
- **Found during:** Task 1 / GREEN phase verification
- **Issue:** Original test assertion `assert "'; alert(" not in fn` was incorrect — `json.dumps` keeps single quotes inside a double-quoted string (they're harmless in JS), so the substring literally appears in the function string even when correctly escaped. The assertion would always fail even with correct json.dumps implementation.
- **Fix:** Changed assertion to verify the key argument starts with a double-quote character (json.dumps output pattern) rather than checking for absence of the raw payload substring.
- **Files modified:** tests/test_phase7_state_capture.py
- **Verification:** Test passes with json.dumps implementation, would fail if f-string single-quote pattern were used
- **Committed in:** 9d89fcc (combined Task 1+2 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - incorrect test assertion)
**Impact on plan:** The fix corrects the test's validation logic so it accurately detects the injection-safe pattern. No scope change, no architecture change.

## Issues Encountered

None beyond the assertion correction documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- PERF-02 and SECR-01 requirements fulfilled
- session_state.py is ready for future session resumption work (Phase 3 roadmap item)
- No blockers

---
*Phase: 04-evaluate-consolidation-security*
*Completed: 2026-03-10*
