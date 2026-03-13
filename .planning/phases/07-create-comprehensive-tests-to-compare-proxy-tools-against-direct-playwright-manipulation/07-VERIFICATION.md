---
phase: 07-create-comprehensive-tests-to-compare-proxy-tools-against-direct-playwright-manipulation
verified: 2026-03-11T10:30:00Z
status: human_needed
score: 5/5 must-haves verified
re_verification: false
human_verification:
  - test: "Run uv run pytest tests/test_comparison.py -v -m integration with playwright-proxy-server running on localhost:34501 and npx available"
    expected: "All 5 scenarios pass: Scenario 1 sees 'Example Domain' on both paths, Scenario 2 proxy second read returns empty string, Scenario 3 unique ref_ids per page, Scenario 4 filtered length < full length, Scenario 5 both paths do not crash on invalid URL"
    why_human: "Integration tests require a live server, npx @playwright/mcp@0.0.68, and internet access to example.com and httpbin.org — cannot run in static analysis"
  - test: "Run uv run pytest tests/test_comparison.py::test_scenario2_diff_behavior -v -m integration"
    expected: "second_read == '' assertion passes (proxy diff cursor suppresses unchanged content)"
    why_human: "Diff suppression depends on SQLite diff_cursors table state — requires actual running proxy server"
  - test: "Run uv run pytest tests/test_comparison.py::test_scenario4_content_search -v -m integration"
    expected: "len(filtered_content) < len(full_content) assertion passes"
    why_human: "search_for parameter filtering requires server's /content endpoint to be live"
---

# Phase 7: Create Comprehensive Comparison Tests Verification Report

**Phase Goal:** Create comprehensive tests to compare proxy tools against direct Playwright manipulation
**Verified:** 2026-03-11T10:30:00Z
**Status:** human_needed (all static checks pass; live test run required to confirm behavior)
**Re-verification:** No — initial verification

## Goal Achievement

The goal is to produce a test suite that proves the proxy faithfully preserves Playwright behavior while demonstrating its value-add features (diff, search, persistence). This requires `tests/test_comparison.py` to exist with substantive, wired comparison scenarios — not stubs.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Proxy navigate+snapshot returns same landmark content as direct Playwright MCP for example.com | VERIFIED (static) | `test_scenario1_simple_navigation` asserts `"Example Domain" in proxy_content` and `"Example Domain" in direct_content`; both paths exercised |
| 2 | Proxy diff suppresses unchanged content on second read while direct always returns full content | VERIFIED (static) | `test_scenario2_diff_behavior` asserts `second_read == ""` for proxy and `len(direct_second) > 0` for direct; key behavioral difference captured |
| 3 | Proxy preserves correct content across multi-page navigation with unique ref_ids per page | VERIFIED (static) | `test_scenario3_multi_page_navigation` asserts `ref_id1 != ref_id2`, checks "Example Domain" and "httpbin" on correct pages for both paths |
| 4 | Proxy search_for parameter filters snapshot to fewer lines than full content | VERIFIED (static) | `test_scenario4_content_search` asserts `len(filtered_content) < len(full_content)` and both contain "Example Domain" |
| 5 | Both proxy and direct handle invalid URL navigation gracefully without crashing | VERIFIED (static) | `test_scenario5_error_handling` uses `proxy_failed_gracefully` + `direct_failed_gracefully` flags with try/except wrapping both paths |

**Score:** 5/5 truths verified (static analysis); live execution requires human

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_comparison.py` | 5 comparison scenarios + DirectPlaywrightClient helper, min 180 lines | VERIFIED | 357 lines, syntax valid, DirectPlaywrightClient class present |

**Level 1 (Exists):** File exists at `tests/test_comparison.py` — confirmed.

**Level 2 (Substantive):** 357 lines (far exceeds 180-line minimum). Contains `DirectPlaywrightClient` class with `start()`, `stop()`, `_initialize()`, `send()`, `call_tool()` methods. Five test functions `test_scenario1` through `test_scenario5`. All contain real assertions on both proxy and direct paths, not stubs. No placeholder comments, TODO markers, or empty return values found.

**Level 3 (Wired):** `asyncio_mode = "auto"` in `pyproject.toml` wires async tests without `@pytest.mark.asyncio`. `BASE_URL = "http://localhost:34501"` with `httpx.AsyncClient(base_url=BASE_URL)` wires proxy path. `asyncio.create_subprocess_exec("npx", "@playwright/mcp@0.0.68", "--headless", ...)` wires direct path. `direct_client` fixture is function-scoped and wired into all 5 test functions via parameter injection.

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `tests/test_comparison.py` | `http://localhost:34501` | `httpx.AsyncClient(base_url=BASE_URL)` where `BASE_URL = "http://localhost:34501"` | WIRED | Lines 97, 159, 190, 233, 277, 329 — all 5 scenarios use `httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT)` |
| `tests/test_comparison.py` | `npx @playwright/mcp@0.0.68` | `asyncio.create_subprocess_exec("npx", "@playwright/mcp@0.0.68", "--headless", ...)` | WIRED | Lines 41-46 in `DirectPlaywrightClient.start()` |

Note: The PLAN pattern `httpx\.AsyncClient.*base_url.*34501` did not match literally because `BASE_URL` is defined on a separate line from the `AsyncClient` call. The link is functionally wired — `BASE_URL = "http://localhost:34501"` at line 97, used in `httpx.AsyncClient(base_url=BASE_URL)` at lines 159, 190, 233, 277, 329.

Also note: `PlaywrightManager` appears only in a docstring comment (`"Mirrors PlaywrightManager.send_request() but without health checks..."`) — it is NOT imported. The no-import requirement is satisfied.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CMP-01 | 07-01-PLAN.md | Proxy and direct return same landmark content for example.com navigation | SATISFIED | `test_scenario1_simple_navigation`: asserts "Example Domain" in both `proxy_content` and `direct_content` |
| CMP-02 | 07-01-PLAN.md | Proxy diff suppresses unchanged content on second read; direct always returns full | SATISFIED | `test_scenario2_diff_behavior`: asserts `second_read == ""` (proxy) and `len(direct_second) > 0` |
| CMP-03 | 07-01-PLAN.md | Both paths correctly reflect page content across multi-page navigation | SATISFIED | `test_scenario3_multi_page_navigation`: navigates example.com then httpbin.org, asserts content and unique ref_ids |
| CMP-04 | 07-01-PLAN.md | Proxy search_for filters snapshot to fewer lines than full response | SATISFIED | `test_scenario4_content_search`: asserts `len(filtered_content) < len(full_content)` |
| CMP-05 | 07-01-PLAN.md | Both paths handle invalid URL navigation gracefully | SATISFIED | `test_scenario5_error_handling`: both proxy and direct paths wrapped in graceful failure detection |

No orphaned requirements: all 5 CMP requirements from REQUIREMENTS.md (lines 49-53) are claimed by 07-01-PLAN.md and implemented in `tests/test_comparison.py`. REQUIREMENTS.md traceability table (lines 102-106) maps all CMP-01 through CMP-05 to Phase 7 as "Planned" — these are now implemented.

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| — | None found | — | — |

Scanned `tests/test_comparison.py` for: TODO/FIXME/HACK comments, placeholder text, empty return values (`return null`, `return {}`, `return []`), stub handlers. None detected.

### Human Verification Required

#### 1. Full Integration Suite Run

**Test:** With `playwright-proxy-server` running on `localhost:34501` and `npx @playwright/mcp@0.0.68` available, run:
```
uv run pytest tests/test_comparison.py -v -m integration
```
**Expected:** All 5 scenarios pass. Total time ~2-3 minutes (live browser + network calls).
**Why human:** Requires live server process, Node.js subprocess, and internet access to `example.com` and `httpbin.org`.

#### 2. Diff Suppression Behavior (Scenario 2)

**Test:** Isolate scenario 2 and inspect the second `GET /content/{ref_id}` response body.
**Expected:** `{"content": ""}` — empty string, not the full accessibility tree.
**Why human:** Depends on SQLite `diff_cursors` table being populated by a real proxy server response cycle.

#### 3. Search Filtering Behavior (Scenario 4)

**Test:** Observe the filtered vs full content lengths in scenario 4 output.
**Expected:** `filtered_content` contains only lines matching "Example Domain" while `full_content` includes the entire accessibility tree.
**Why human:** The `/content/{ref_id}?search_for=...` parameter behavior requires the server's search implementation to be live.

#### 4. Browser Profile Isolation (Two Playwright Processes)

**Test:** During scenario 1, observe server logs and direct client stderr for "browser already running" or profile contention errors.
**Expected:** No profile contention errors; two separate Chromium instances run independently.
**Why human:** The RESEARCH.md documents this as a known pitfall (Pitfall #1); `--headless` is the mitigation but may not be sufficient in all environments.

### Gaps Summary

No structural gaps found. The file exists, is substantive (357 lines), implements all 5 scenarios with both proxy and direct paths, satisfies all 5 CMP requirements, and contains no stubs or anti-patterns.

The phase goal is structurally achieved. Behavioral correctness at runtime (whether the assertions actually pass against a live server and live Playwright subprocess) requires human verification via the integration test run.

---

_Verified: 2026-03-11T10:30:00Z_
_Verifier: Claude (gsd-verifier)_
