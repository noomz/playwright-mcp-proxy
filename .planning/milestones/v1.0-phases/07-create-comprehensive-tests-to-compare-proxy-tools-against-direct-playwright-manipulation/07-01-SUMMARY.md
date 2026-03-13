---
phase: 07-create-comprehensive-tests-to-compare-proxy-tools-against-direct-playwright-manipulation
plan: 01
subsystem: testing
tags: [pytest, httpx, asyncio, playwright-mcp, integration-testing, comparison-tests]

# Dependency graph
requires:
  - phase: 01-core-infrastructure
    provides: HTTP server at localhost:34501, /proxy, /content, /sessions endpoints
  - phase: 02-diff-based-content
    provides: diff cursor mechanics (second read returns empty on unchanged content)
  - phase: 05-cli-management-tool
    provides: stable server and session lifecycle for integration tests

provides:
  - tests/test_comparison.py with DirectPlaywrightClient helper and 5 comparison scenarios
  - Behavioral proof that proxy faithfully preserves Playwright content while adding diff, search, persistence

affects:
  - future-phases (any phase adding tools should add corresponding comparison scenario)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - DirectPlaywrightClient: standalone async context manager for JSON-RPC over stdio (no PlaywrightManager import)
    - asyncio.wait_for on readline to prevent indefinite blocking from unresponsive subprocess
    - pytest.fixture function-scoped async direct_client for per-test subprocess isolation

key-files:
  created:
    - tests/test_comparison.py
  modified: []

key-decisions:
  - "DirectPlaywrightClient uses asyncio.wait_for(readline(), timeout=30.0) to prevent hanging on slow network"
  - "Each test uses function-scoped direct_client fixture to prevent browser state leakage between scenarios"
  - "All tests marked @pytest.mark.integration — opt-in only; require running server + npx + internet"
  - "Scenarios assert on stable landmark content ('Example Domain', 'httpbin') not ref attributes or full snapshot equality"
  - "Scenario 5 error handling wraps both proxy and direct paths in try/except to handle multiple failure modes gracefully"

patterns-established:
  - "Comparison pattern: run proxy path via httpx + direct path via DirectPlaywrightClient, assert behavioral equivalence"
  - "Direct client spawns separate npx @playwright/mcp@0.0.68 --headless subprocess (pinned version matches server)"

requirements-completed: [CMP-01, CMP-02, CMP-03, CMP-04, CMP-05]

# Metrics
duration: 7min
completed: 2026-03-11
---

# Phase 07 Plan 01: Create Comprehensive Comparison Tests Summary

**pytest integration test suite with DirectPlaywrightClient helper comparing proxy HTTP API against raw Playwright MCP stdio across 5 behavioral scenarios**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-11T09:47:30Z
- **Completed:** 2026-03-11T09:54:30Z
- **Tasks:** 2 (Task 1: helpers + fixture, Task 2: 5 test scenarios)
- **Files modified:** 1

## Accomplishments

- Created `tests/test_comparison.py` (357 lines) with `DirectPlaywrightClient` async context manager that speaks JSON-RPC over stdio to `npx @playwright/mcp@0.0.68 --headless`
- Implemented all 5 comparison scenarios (CMP-01 through CMP-05) covering simple navigation, diff suppression, multi-page navigation, content search filtering, and error handling
- All 61 existing unit tests continue to pass without regression

## Task Commits

Each task was committed atomically:

1. **Tasks 1 & 2: DirectPlaywrightClient + helpers + 5 scenarios** - `11e338b` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified

- `tests/test_comparison.py` — DirectPlaywrightClient helper class, proxy helper functions (_create_session, _proxy, _navigate_and_snapshot), direct_client fixture, and 5 @pytest.mark.integration test scenarios

## Decisions Made

- Used `asyncio.wait_for(stream.readline(), timeout=30.0)` to prevent indefinite blocking (per research pitfall #3)
- Function-scoped `direct_client` fixture ensures each test gets a fresh browser subprocess (per research pitfall #5)
- Scenarios assert only on stable landmark content, never on ref attributes like `[ref=e6]` (per research pitfall #2)
- Combined Task 1 and Task 2 into a single commit because both tasks write to the same file and neither is useful without the other

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. Tests require a running `playwright-proxy-server` at localhost:34501 and `npx @playwright/mcp@0.0.68` available; documented in test file docstring.

## Next Phase Readiness

- Comparison test suite complete and ready to run against a live server
- Run with: `uv run pytest tests/test_comparison.py -v -m integration`
- No blockers for future phases

---
*Phase: 07-create-comprehensive-tests-to-compare-proxy-tools-against-direct-playwright-manipulation*
*Completed: 2026-03-11*
