---
phase: 08-add-new-perf-comparison-results-between-claude-in-chrome
plan: 01
status: complete
started: 2026-03-12
completed: 2026-03-12
duration: ~15min
---

# Summary: 08-01 Chrome Comparison Tests

## What Was Built

Added chrome-in-chrome measurement infrastructure to the Phase 7 comparison framework:

1. **Test file** (`tests/test_chrome_comparison.py`): Loads pre-recorded chrome measurements from JSON fixture, validates schema, and prints formatted chrome-path performance tables
2. **Measurement fixture** (`tests/chrome_measurements.json`): Real timing data from live Chrome browser via claude-in-chrome extension across 3 scenarios
3. **Pytest marker** (`chrome_comparison`): Registered in pyproject.toml for opt-in test selection

## Key Files

### Created
- `tests/test_chrome_comparison.py` — Chrome comparison test with JSON loader, validation, and report formatter
- `tests/chrome_measurements.json` — Pre-recorded measurements for example.com, Google Search, YouTube Search

### Modified
- `pyproject.toml` — Added `chrome_comparison` marker

## Measurements Recorded

| Scenario | Operations | Total Latency | Max Payload |
|----------|-----------|---------------|-------------|
| example.com | 3 (navigate, read_page, get_page_text) | ~7s | 213 bytes |
| Google Search | 5 (navigate x2, read_page x2, form_input) | ~26s | 12,000 bytes |
| YouTube Search | 5 (navigate x2, read_page x2, form_input) | ~10s | 11,000 bytes |

## Deviations

- `form_input` on Google did not trigger search submission; used direct URL navigation for search results instead
- Timing measured via JS timestamp deltas minus baseline overhead (~6150ms for 2 JS round-trips), not direct tool call timing

## Self-Check: PASSED

- [x] chrome_measurements.json loads without error
- [x] All measurements have path="chrome"
- [x] 3 scenarios with at least 2 measurements each
- [x] `uv run pytest tests/test_chrome_comparison.py -v -m chrome_comparison` passes
- [x] All 86 existing tests unaffected
