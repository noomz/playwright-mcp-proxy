# Phase 02: Bug Fixes - Research

**Researched:** 2026-03-10
**Domain:** Python/FastAPI — data serialization, SQLite query, plain-text log parsing
**Confidence:** HIGH

## Summary

All three bugs are localized to two files: `playwright_mcp_proxy/server/app.py` and (for BUGF-02 only) a missing call pattern in `app.py`. The root causes are fully visible in the source and the fixes are mechanical one- to three-line changes.

**BUGF-01** is a single-line serialization mistake: `str(request.params)` produces Python repr syntax (single quotes, `True`/`False`, `None`) rather than valid JSON. Replace with `json.dumps(request.params)`.

**BUGF-02** requires two cooperating changes: (a) call the existing `database.get_console_error_count(ref_id)` method which already exists in `operations.py`, and (b) understand that this method queries the normalized `console_logs` table — which is currently never populated from `browser_console_messages` responses. A two-sub-task approach is needed: (1) replace the hardcoded `0` with the DB call, and (2) parse the blob stored in `responses.console_logs` into the normalized table at write time.

**BUGF-03** is a fallback path TODO in `get_console_content`: when no normalized rows exist, the raw text blob from Playwright is returned unfiltered. The blob format is now fully known (plain text, not JSON), so the parser can be implemented precisely.

**Primary recommendation:** Fix all three bugs in a single plan with sequential tasks — BUGF-01 is independent; BUGF-02 and BUGF-03 share the console log parsing logic and should be implemented together.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| BUGF-01 | Request params serialized via `json.dumps()` instead of `str()` for valid JSON storage | Single line change in `app.py` line 435; `json` module already imported |
| BUGF-02 | `console_error_count` in proxy response metadata reflects actual error count from stored logs | `get_console_error_count()` already exists in `operations.py`; requires blob parsing at write time to populate normalized table |
| BUGF-03 | Console log level filtering parses raw blob in fallback path when no normalized logs exist | Blob format confirmed from `@playwright/mcp` source: plain text, one line per message with `[LEVEL]` prefix; `shouldIncludeMessage` severity ordering documented |
</phase_requirements>

## Standard Stack

### Core (already in project)

| Library | Version | Purpose | Role in Fixes |
|---------|---------|---------|--------------|
| Python `json` | stdlib | JSON serialization/deserialization | BUGF-01: `json.dumps()`, BUGF-03: not needed (blob is plain text) |
| `aiosqlite` | >=0.21.0 | Async SQLite | BUGF-02: `get_console_error_count()` uses it |
| `pytest-asyncio` | >=1.0.0 | Async test runner | All tests use `asyncio_mode = "auto"` |
| `pytest` | >=8.3.0 | Test framework | Existing test fixtures reusable |

No new dependencies required for any of the three fixes.

## Architecture Patterns

### BUGF-01: Params Serialization (app.py line 435)

**What:** `str(request.params)` converts a Python `dict` to Python repr, not JSON.

**Root cause (confirmed, HIGH confidence):**
```python
# app.py line 431-437
db_request = Request(
    ref_id=ref_id,
    session_id=request.session_id,
    tool_name=request.tool,
    params=str(request.params),  # BUG: produces {'url': 'https://...'} not valid JSON
    timestamp=datetime.now(),
)
```

Python `str({'url': 'https://example.com'})` yields `"{'url': 'https://example.com'}"` — single quotes, not double quotes. `json.loads()` will raise `json.JSONDecodeError` on this string.

**Fix:**
```python
params=json.dumps(request.params),  # json module already imported at top of app.py
```

**Verification:** `json.loads(json.dumps(d)) == d` is true for any dict of JSON-compatible values.

### BUGF-02: Console Error Count (app.py line 485)

**What:** Hardcoded `console_error_count=0` never reflects actual errors.

**Root cause (confirmed, HIGH confidence):**
```python
# app.py line 481-486
metadata = ResponseMetadata(
    tool=request.tool,
    has_snapshot=page_snapshot is not None,
    has_console_logs=console_logs_data is not None,
    console_error_count=0,  # BUG: hardcoded TODO
)
```

**Why the existing `get_console_error_count()` won't fix it alone:** The method queries the normalized `console_logs` table:
```python
# operations.py line 298-305
async def get_console_error_count(self, ref_id: str) -> int:
    async with self.conn.execute(
        "SELECT COUNT(*) as count FROM console_logs WHERE ref_id = ? AND level = 'error'",
        (ref_id,),
    ) as cursor:
        row = await cursor.fetchone()
        return row["count"] if row else 0
```

The proxy endpoint stores console logs in `responses.console_logs` (raw blob) but **never inserts rows into `console_logs` table**. Therefore `get_console_error_count()` always returns 0.

**Fix strategy:** Parse the raw blob at write time and insert into `console_logs` table, then call `get_console_error_count()`.

The correct pattern is:
1. After storing `db_response`, if `console_logs_data` is not None, parse it and batch-insert into `console_logs` table
2. Then call `await database.get_console_error_count(ref_id)` for the metadata

### BUGF-03: Console Log Level Filtering in Fallback Path

**What:** `get_console_content` fallback ignores the `level` parameter.

**Root cause (confirmed, HIGH confidence):**
```python
# app.py line 666-670
if response.console_logs:
    content = response.console_logs
    # TODO: Parse JSON and filter by level if needed
    return {"content": content}
```

**Console log blob format (confirmed from `@playwright/mcp` v0.0.68 source):**

The blob is **plain text**, not JSON. It is produced by `console.js` (tool handler) as:
```
Total messages: N (Errors: E, Warnings: W)
Returning M messages for level "info"

[TYPE_UPPERCASE] message text @ url:lineNumber
[TYPE_UPPERCASE] message text @ url:lineNumber
...
```

For page errors (unhandled exceptions), the format is:
```
Error stack trace or message (no bracket prefix)
```

The `messageToConsoleMessage` function in `tab.js` confirms the `toString()` pattern:
```javascript
toString: () => `[${message.type().toUpperCase()}] ${message.text()} @ ${message.location().url}:${message.location().lineNumber}`
```

**Level hierarchy (confirmed from `tab.js`):**
```
consoleMessageLevels = ["error", "warning", "info", "debug"]  // index 0 = most severe
shouldIncludeMessage: messageLevel index <= thresholdLevel index
```

So `level="error"` returns only errors; `level="info"` returns error + warning + info; `level="debug"` returns all.

**Level prefix mapping:**
- `[ERROR]` or `[ASSERT]` → error severity
- `[WARNING]` → warning severity
- `[LOG]`, `[INFO]`, `[COUNT]`, `[DIR]`, etc. → info severity
- `[DEBUG]`, `[TRACE]`, `[CLEAR]` → debug severity

**Fix approach:** Parse the blob line by line. Skip the header lines (lines starting with "Total messages:" or "Returning "). For remaining lines, check the `[LEVEL]` prefix. Apply the severity ordering filter. Return matching lines joined by newline.

Shared parsing logic between BUGF-02 and BUGF-03: extract the same regex-based line parser into a helper function.

### Anti-Patterns to Avoid

- **Treating the blob as JSON:** It is plain text. `json.loads(console_logs_data)` will raise `JSONDecodeError`. Do not attempt JSON parsing on the blob.
- **Calling `get_console_error_count()` before inserting rows:** Always parse and insert into `console_logs` table first, then count.
- **Using exact string match for level filtering:** Use the severity-ordered inclusion (`index <=`) matching Playwright's own logic, not exact equality.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization | Custom dict-to-string | `json.dumps()` | Already imported; handles edge cases (None → null, True → true) |
| Async DB operations | Synchronous wrappers | Existing `Database` methods | `create_console_logs_batch()` and `get_console_error_count()` already exist |
| Test fixtures | New fixture setup | Existing `db` fixture in `test_database.py` / `test_diff.py` | Pattern is established; use same `tempfile` + `init_database` approach |

**Key insight:** All infrastructure (DB methods, models, import statements) already exists. These are all call-site fixes, not new component development.

## Common Pitfalls

### Pitfall 1: BUGF-02 — Assuming normalized table is populated
**What goes wrong:** Call `get_console_error_count(ref_id)` without first inserting rows into `console_logs` table — still returns 0.
**Why it happens:** The proxy endpoint stores logs as blob only; no parser call exists.
**How to avoid:** Insert via `create_console_logs_batch()` before calling the count method.
**Warning signs:** Test returns 0 even after fixing the hardcode.

### Pitfall 2: BUGF-03 — The header lines
**What goes wrong:** Parser treats "Total messages: 3 (Errors: 1, Warnings: 0)" as a log line and tries to match `[LEVEL]` prefix — fails or emits noise.
**Why it happens:** The blob starts with 1-2 header lines before the blank separator line.
**How to avoid:** Skip lines that don't start with `[` (or skip until past the blank line after the header block).

### Pitfall 3: BUGF-03 — Level name mismatch
**What goes wrong:** Playwright uses `"warning"` internally but the blob says `[WARNING]`. The `console_logs` schema CHECK constraint is `level IN ('debug', 'info', 'warn', 'error')`. Note: Playwright type is `"warning"` but the schema expects `"warn"`.
**Why it happens:** Schema uses abbreviated `warn`; Playwright uses full `warning`.
**How to avoid:** Normalize `warning` → `warn` when inserting into `console_logs` table. Keep `warning` for raw text parsing from blob.

### Pitfall 4: BUGF-01 — Existing stored data
**What goes wrong:** Fix is applied going forward but existing rows in `requests.params` are still invalid JSON.
**Why it happens:** The bug has been present since initial implementation.
**How to avoid:** The fix only affects new writes. No migration needed — out of scope per requirements.

## Code Examples

### BUGF-01 Fix Pattern
```python
# Source: app.py line 435 — confirmed from source inspection
# Before (BUG):
params=str(request.params),

# After (FIX):
params=json.dumps(request.params),
# json is already imported at line 6 of app.py
```

### BUGF-02 + BUGF-03 Shared Parser

The same parsing logic is needed for both bugs. Suggested helper (to be placed in `app.py` or a shared utility):

```python
# Severity order matches Playwright's consoleMessageLevels
CONSOLE_LEVEL_ORDER = ["error", "warning", "info", "debug"]

def _get_level_from_prefix(line: str) -> str | None:
    """Extract Playwright level from [LEVEL] prefix. Returns normalized level or None."""
    if not line.startswith("["):
        return None
    bracket_end = line.find("]")
    if bracket_end == -1:
        return None
    prefix = line[1:bracket_end].lower()
    # Normalize Playwright types to schema levels
    if prefix in ("error", "assert"):
        return "error"
    elif prefix == "warning":
        return "warn"      # schema uses 'warn' not 'warning'
    elif prefix in ("debug", "trace", "clear", "endgroup", "profile",
                    "profileend", "startgroup", "startgroupcollapsed"):
        return "debug"
    else:
        return "info"      # log, info, count, dir, dirxml, table, time, timeend, etc.


def _parse_console_blob(blob: str) -> list[dict]:
    """Parse plain-text console log blob into structured entries."""
    entries = []
    lines = blob.split("\n")
    # Skip header lines (don't start with '[')
    for line in lines:
        if not line.strip():
            continue
        level = _get_level_from_prefix(line)
        if level is None:
            continue  # header or unrecognized line
        entries.append({"level": level, "text": line})
    return entries


def _filter_console_blob_by_level(blob: str, threshold_level: str) -> str:
    """Filter blob lines by severity threshold (matches Playwright's shouldIncludeMessage)."""
    if not blob:
        return ""
    threshold_idx = CONSOLE_LEVEL_ORDER.index(threshold_level) if threshold_level in CONSOLE_LEVEL_ORDER else 2
    result_lines = []
    for line in blob.split("\n"):
        if not line.strip():
            continue
        level = _get_level_from_prefix(line)
        if level is None:
            continue
        # Use 'warn' for comparison but index lookup needs 'warning'
        lookup_level = "warning" if level == "warn" else level
        # CONSOLE_LEVEL_ORDER uses 'warning'; need consistent indexing
        msg_idx = CONSOLE_LEVEL_ORDER.index(lookup_level) if lookup_level in CONSOLE_LEVEL_ORDER else 2
        if msg_idx <= threshold_idx:
            result_lines.append(line)
    return "\n".join(result_lines)
```

Note: The level ordering array for lookups must be consistent. Use `warning` in the ordering array for index lookups, but normalize to `warn` only for DB schema insertion.

### BUGF-02: Populating the normalized table

```python
# After creating db_response, if console_logs_data exists:
if console_logs_data:
    entries = _parse_console_blob(console_logs_data)
    logs = [
        ConsoleLog(
            ref_id=ref_id,
            level=entry["level"],
            message=entry["text"],
            timestamp=datetime.now(),
        )
        for entry in entries
    ]
    if logs:
        await database.create_console_logs_batch(logs)

# Now the count is accurate:
error_count = await database.get_console_error_count(ref_id)
metadata = ResponseMetadata(
    tool=request.tool,
    has_snapshot=page_snapshot is not None,
    has_console_logs=console_logs_data is not None,
    console_error_count=error_count,
)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `str(params)` | `json.dumps(params)` | Phase 2 | Stored params become `json.loads()`-safe |
| Hardcoded `console_error_count=0` | DB-backed count from normalized table | Phase 2 | Metadata reflects reality |
| Unfiltered blob fallback | Level-filtered blob parsing | Phase 2 | `GET /console/{ref_id}?level=error` works correctly |

## Open Questions

1. **Level ordering constant placement**
   - What we know: `CONSOLE_LEVEL_ORDER` is needed in both the proxy endpoint (BUGF-02) and the console endpoint (BUGF-03), both in `app.py`
   - What's unclear: Whether to inline or extract to a helper module
   - Recommendation: Define once at module level in `app.py` for Phase 2 scope; extract to utils only if Phase 3 needs it

2. **Warning level naming inconsistency**
   - What we know: Playwright uses `"warning"` in type names; schema `CHECK` constraint uses `'warn'`; blob text uses `[WARNING]`
   - What's unclear: Whether any existing `console_logs` rows use `"warning"` (schema would reject them)
   - Recommendation: Normalize to `"warn"` on insert; use `"warning"` only in the CONSOLE_LEVEL_ORDER index array for severity comparisons

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.0+ with pytest-asyncio 1.0.0+ |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` — `asyncio_mode = "auto"`) |
| Quick run command | `uv run pytest tests/ -x` |
| Full suite command | `uv run pytest tests/ --cov=playwright_mcp_proxy` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BUGF-01 | `json.dumps(params)` stores valid JSON — `json.loads()` succeeds | unit | `uv run pytest tests/test_bugs.py::test_request_params_valid_json -x` | Wave 0 |
| BUGF-01 | `str(params)` is invalid JSON (regression guard) | unit | `uv run pytest tests/test_bugs.py::test_request_params_str_is_invalid_json -x` | Wave 0 |
| BUGF-02 | `console_error_count` returns actual count after log parsing | unit | `uv run pytest tests/test_bugs.py::test_console_error_count_nonzero -x` | Wave 0 |
| BUGF-02 | `console_error_count` returns 0 when no errors | unit | `uv run pytest tests/test_bugs.py::test_console_error_count_zero -x` | Wave 0 |
| BUGF-03 | Level filter `error` returns only error lines from blob | unit | `uv run pytest tests/test_bugs.py::test_console_blob_filter_error_only -x` | Wave 0 |
| BUGF-03 | Level filter `info` returns error + warning + info lines | unit | `uv run pytest tests/test_bugs.py::test_console_blob_filter_info_includes_errors -x` | Wave 0 |
| BUGF-03 | No level filter returns all lines | unit | `uv run pytest tests/test_bugs.py::test_console_blob_filter_no_level -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_bugs.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** `uv run pytest tests/ --cov=playwright_mcp_proxy` green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_bugs.py` — new test file covering all BUGF-01, BUGF-02, BUGF-03 behaviors listed above
- [ ] No framework install needed — pytest and pytest-asyncio already in `[dev]` dependencies

## Sources

### Primary (HIGH confidence)
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/playwright_mcp_proxy/server/app.py` — lines 435, 485, 666-670 (bug sites confirmed from source)
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/playwright_mcp_proxy/database/operations.py` — `get_console_error_count()` at line 298, `create_console_logs_batch()` at line 253
- `~/.npm/_npx/84539a01c0e4c364/node_modules/playwright/lib/mcp/browser/tools/console.js` — blob format confirmed: plain text, header line, then `message.toString()` per line
- `~/.npm/_npx/84539a01c0e4c364/node_modules/playwright/lib/mcp/browser/tab.js` — `messageToConsoleMessage` (line 339), `shouldIncludeMessage` (line 372), `consoleMessageLevels` (line 371), `consoleLevelForMessageType` (line 376)
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/playwright_mcp_proxy/database/schema.py` — `console_logs` level CHECK constraint: `('debug', 'info', 'warn', 'error')` — `warn` not `warning`

### Secondary (MEDIUM confidence)
- Python stdlib `json` module documentation — `json.dumps()` / `json.loads()` round-trip behavior

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; all tools in use
- Architecture: HIGH — bug sites confirmed from source code; Playwright blob format confirmed from installed package source
- Pitfalls: HIGH — confirmed from schema constraints and Playwright internals

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable codebase; @playwright/mcp pinned to 0.0.68)
