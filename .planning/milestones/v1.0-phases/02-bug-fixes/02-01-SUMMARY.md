---
phase: 02-bug-fixes
plan: 01
subsystem: server
tags: [bug-fix, serialization, console-logs, sqlite, tdd]
dependency_graph:
  requires: []
  provides: [BUGF-01, BUGF-02, BUGF-03]
  affects: [playwright_mcp_proxy/server/app.py, tests/test_bugs.py]
tech_stack:
  added: []
  patterns: [console-blob-parser, level-severity-ordering, tdd-red-green]
key_files:
  created:
    - tests/test_bugs.py
  modified:
    - playwright_mcp_proxy/server/app.py
decisions:
  - "Used CONSOLE_LEVEL_ORDER = [error, warning, info, debug] severity ordering matching Playwright's consoleMessageLevels"
  - "Schema uses 'warn' not 'warning'; normalize on insert, translate back for CONSOLE_LEVEL_ORDER lookup"
  - "_get_level_from_prefix handles edge cases: assert->error, trace/clear/endgroup->debug, log/count/dir->info"
  - "Inline import of ConsoleLog moved to top-level import alongside other DB models"
metrics:
  duration: 2min
  completed_date: "2026-03-10"
  tasks_completed: 2
  files_modified: 2
---

# Phase 02 Plan 01: Bug Fixes (BUGF-01, BUGF-02, BUGF-03) Summary

**One-liner:** Fixed params stored as invalid Python repr, console error count always returning 0, and console log level filtering broken in blob fallback path.

## What Was Built

Three data-integrity fixes to `playwright_mcp_proxy/server/app.py`, with 8 tests covering all three bugs.

### BUGF-01: Params Serialization
`str(request.params)` was storing Python dict repr (single-quoted keys) instead of valid JSON. Changed to `json.dumps(request.params)`. The `json` module was already imported.

### BUGF-02: Console Error Count
`console_error_count` was hardcoded to `0` in proxy response metadata. Now:
1. After storing response, calls `_parse_console_blob(console_logs_data)` to extract structured entries
2. Batch-inserts entries via `database.create_console_logs_batch(logs)`
3. Queries `database.get_console_error_count(ref_id)` for the actual count

### BUGF-03: Console Log Level Filtering (Fallback Path)
The fallback path in `get_console_content` had a `# TODO: Parse JSON and filter by level` comment and returned the raw blob unfiltered. Now calls `_filter_console_blob_by_level(response.console_logs, level)` which:
- Parses each line by `[LEVEL]` prefix
- Applies severity threshold ordering (`error < warning < info < debug`)
- Returns only lines at or above the requested threshold

### New Functions Added

| Function | Purpose |
|---|---|
| `_get_level_from_prefix(line)` | Extracts normalized DB-compatible level from `[LEVEL]` prefix |
| `_parse_console_blob(blob)` | Parses plain-text blob into `[{level, text}]` entries |
| `_filter_console_blob_by_level(blob, level)` | Filters blob lines by severity threshold |
| `CONSOLE_LEVEL_ORDER` | Severity ordering constant: `[error, warning, info, debug]` |

## Verification

```
uv run pytest tests/test_bugs.py -v  # 8 passed
uv run pytest tests/ -x              # 38 passed (zero regressions)
uv run ruff check playwright_mcp_proxy/server/app.py  # All checks passed
```

## Commits

| Task | Commit | Description |
|---|---|---|
| Task 1 (RED) | 8da3204 | test(02-01): add failing tests for BUGF-01, BUGF-02, BUGF-03 |
| Task 2 (GREEN) | 1a8e426 | fix(02-01): fix param serialization, console error count, and log level filtering |

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED
