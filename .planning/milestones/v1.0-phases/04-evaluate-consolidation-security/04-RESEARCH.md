# Phase 4: Evaluate Consolidation & Security - Research

**Researched:** 2026-03-10
**Domain:** JavaScript evaluation via Playwright MCP, JS injection prevention
**Confidence:** HIGH

## Summary

Phase 4 targets two closely related changes in `session_state.py`: combining 5 sequential `browser_evaluate` RPCs into one, and eliminating JS injection risk in `restore_state()`. Both changes are in the same file and same class (`SessionStateManager`). The implementation is self-contained and straightforward.

The `browser_evaluate` tool in `@playwright/mcp@0.0.68` accepts only a `function` string (plus optional `element` and `ref`). There is no `arg` parameter. This means data must be embedded inside the JS function string. The safe pattern embeds data using `json.dumps()` to produce a JSON literal — not f-string interpolation — so special characters in user data cannot escape the JS string context.

For the consolidation change, a single combined JS function returns all 5 state properties as one object, with per-property try/catch so that failure in one property (e.g., accessing `localStorage` on a restricted origin) does not drop the other properties.

**Primary recommendation:** Replace the 5 `send_request` calls in `capture_state()` with one call returning a JSON object of all properties. In `restore_state()`, replace all f-string interpolation with `json.dumps()` embedding of key/value data before embedding in the JS function string.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PERF-02 | Session state capture combines 5 sequential `browser_evaluate` RPCs into single call | Combined JS function pattern documented in Architecture Patterns section |
| SECR-01 | `restore_state()` uses JSON embedding pattern instead of f-string interpolation to prevent JS injection | JSON embedding pattern documented with code example, `json.dumps()` confirmed as correct approach |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `json` (stdlib) | built-in | Serialize Python data to JSON literals for JS embedding | `json.dumps()` produces valid JS values that are also valid JSON; no injection risk |
| `@playwright/mcp` | 0.0.68 (pinned) | browser_evaluate tool for JS execution | Already used; this phase modifies how it is called |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` + `unittest.mock.AsyncMock` | existing | Unit-test new combined capture and injection-safe restore | All new behavior must be covered by mocked tests |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `json.dumps()` embedding | f-string with manual escaping | Manual escaping is fragile; `json.dumps()` handles all edge cases (newlines, quotes, Unicode) automatically |
| Single combined JS call | Parallel async RPCs | Playwright manager serializes calls under `self._lock`; parallel calls are not possible without architecture changes |

**Installation:** No new dependencies required.

## Architecture Patterns

### browser_evaluate Tool Schema (VERIFIED from installed source)

Source: `/Users/noomz/.npm/_npx/84539a01c0e4c364/node_modules/playwright/lib/mcp/browser/tools/evaluate.js`

```javascript
// Actual schema — there is NO `arg` parameter
const evaluateSchema = z.object({
  function: z.string(),      // Required: JS arrow function string
  element: z.string().optional(),
  ref: z.string().optional()
});
```

The tool calls `receiver._evaluateFunction(params.function)` and returns `JSON.stringify(result, null, 2)`. This means:
- The function must be a self-contained JavaScript expression
- Return value is serialized to JSON text and placed in `content[0].text`
- No native arg passing is available

### Pattern 1: Combined Capture — One JS function returning all properties

**What:** A single `browser_evaluate` call with a JS function that collects all 5 state properties into one object.

**When to use:** Any time multiple independent browser properties need to be captured atomically with failure isolation.

**Example:**
```python
# Source: derived from Playwright MCP evaluate.js schema constraints
result = await self.playwright.send_request(
    "tools/call",
    {
        "name": "browser_evaluate",
        "arguments": {
            "function": """() => {
                const state = {};
                try { state.url = window.location.href; } catch(e) { state.url = null; }
                try { state.cookies = document.cookie; } catch(e) { state.cookies = ""; }
                try { state.localStorage = JSON.stringify(localStorage); } catch(e) { state.localStorage = "{}"; }
                try { state.sessionStorage = JSON.stringify(sessionStorage); } catch(e) { state.sessionStorage = "{}"; }
                try { state.viewport = JSON.stringify({width: window.innerWidth, height: window.innerHeight}); } catch(e) { state.viewport = "{}"; }
                return state;
            }""",
        },
    },
)
raw_text = self._extract_evaluate_result(result)
state = json.loads(raw_text)  # Playwright returns JSON.stringify(result)
```

**Key detail:** Playwright MCP calls `JSON.stringify(result, null, 2)` on the return value and places it in `content[0].text`. A returned JS object becomes a JSON string. `_extract_evaluate_result()` returns this text, which must then be parsed with `json.loads()` on the Python side.

### Pattern 2: JSON Embedding for Safe Data Passing

**What:** When a restore operation needs to pass Python data into a JS function string, embed it as a JSON literal produced by `json.dumps()`.

**When to use:** Any time Python variables (keys, values, cookie strings) are interpolated into JS code.

**Current broken pattern (f-string interpolation):**
```python
# BROKEN — JS injection if value contains ', \, or JS-special chars
value_escaped = value.replace("\\", "\\\\").replace("'", "\\'")
f"() => localStorage.setItem('{key}', '{value_escaped}')"
```

**Safe pattern (JSON embedding):**
```python
# SAFE — json.dumps() produces a valid JS string literal
import json

def _make_set_item_fn(storage_type: str, key: str, value: str) -> str:
    k = json.dumps(key)    # e.g., "myKey" or "my\"quoted\"key"
    v = json.dumps(value)  # handles ', \, Unicode, newlines, etc.
    return f"() => {storage_type}.setItem({k}, {v})"

# Cookie example
def _make_set_cookie_fn(name: str, value: str) -> str:
    cookie_str = json.dumps(f"{name}={value}")
    return f"() => document.cookie = {cookie_str}"
```

`json.dumps()` produces valid JavaScript string literals: a JSON string `"hello \"world\""` is also a valid JS string literal. This eliminates the injection surface entirely.

### Pattern 3: Bulk Restore via Single Evaluate (Alternative)

Instead of one `browser_evaluate` per storage key, restore all localStorage keys in a single call:

```python
def _make_restore_storage_fn(storage_type: str, data: dict) -> str:
    # Embed entire dict as JSON literal
    data_json = json.dumps(data)
    return f"""() => {{
        const data = {data_json};
        Object.entries(data).forEach(([k, v]) => {storage_type}.setItem(k, v));
    }}"""
```

This reduces RPC count for restore proportionally to the number of storage keys.

### Anti-Patterns to Avoid

- **String escaping instead of JSON serialization:** Any manual escaping (replacing `'` with `\'`) is fragile and can be bypassed. Use `json.dumps()`.
- **Assuming `arg` parameter exists:** The `browser_evaluate` schema has no `arg` field. Do not reference it.
- **Parsing JSON twice:** `_extract_evaluate_result()` returns the raw text from Playwright. When the JS returns an object, this text IS the JSON string — call `json.loads()` once.
- **Outer try/catch hiding all failures:** Use per-property try/catch so partial state is still captured when one property fails.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JS string escaping | Custom escaping logic | `json.dumps(value)` | JSON strings are valid JS string literals; handles all edge cases including Unicode and control chars |
| JS object serialization | Manual dict → JS object | `json.dumps(data)` | Correct, tested, handles all Python types |
| Parsing Playwright evaluate output | Custom text parser | `json.loads(text)` | Playwright already `JSON.stringify`s the return value |

**Key insight:** `json.dumps()` is both the Python serializer and the JS literal generator. A Python string serialized with `json.dumps()` is always a syntactically valid JavaScript string literal.

## Common Pitfalls

### Pitfall 1: `_extract_evaluate_result` Returns Stringified JSON for Object Returns

**What goes wrong:** When the combined capture JS function returns an object, Playwright calls `JSON.stringify(result)` and puts the result in `content[0].text`. Code that just uses the text as-is will get a raw JSON string, not a Python dict.

**Why it happens:** `_extract_evaluate_result()` was written for scalar returns (URL string, cookie string). It returns `result["content"][0]["text"]` directly. For the combined function, that text is `'{"url": "...", "cookies": "...", ...}'`.

**How to avoid:** After calling `_extract_evaluate_result()` on the combined call, run `json.loads()` on the returned text to get a Python dict.

**Warning signs:** `state["url"]` raising `TypeError: string indices must be integers` means the text was not parsed.

### Pitfall 2: localStorage/sessionStorage Not Accessible from Some Pages

**What goes wrong:** `localStorage` throws `SecurityError` on `about:blank`, `chrome://` URLs, and cross-origin iframes.

**Why it happens:** Browser security policy restricts storage API access on certain origins.

**How to avoid:** Wrap each property in its own try/catch inside the combined JS function. Return `null` or `"{}"` as fallback. Python side treats `null` as "not captured" and skips restoring that property.

**Warning signs:** `capture_state()` returning `None` when the page is `about:blank`.

### Pitfall 3: Partial State Object from Combined Call

**What goes wrong:** If the combined JS function uses a single outer try/catch, one property failure rolls back all properties, returning `None` instead of partial state.

**Why it happens:** Single try/catch is the obvious pattern but is too coarse.

**How to avoid:** Per-property try/catch blocks as shown in Pattern 1. Each block sets the property to a fallback on failure.

### Pitfall 4: Existing Tests Assert `call_count == 5`

**What goes wrong:** `test_capture_state` and `test_capture_state_empty_cookies` both have `assert mock_playwright.send_request.call_count == 5`. After consolidation this becomes `call_count == 1`.

**Why it happens:** Tests were written to match the current 5-call implementation.

**How to avoid:** Update those two assertions to `call_count == 1`. Also update the mock's `side_effect` — the single combined call must return a dict with all 5 keys rather than routing by function text.

## Code Examples

### Combined capture call
```python
# Source: session_state.py capture_state() — after this phase
combined_result = await self.playwright.send_request(
    "tools/call",
    {
        "name": "browser_evaluate",
        "arguments": {
            "function": """() => {
                const s = {};
                try { s.url = window.location.href; } catch(e) { s.url = null; }
                try { s.cookies = document.cookie; } catch(e) { s.cookies = ""; }
                try { s.localStorage = JSON.stringify(localStorage); } catch(e) { s.localStorage = "{}"; }
                try { s.sessionStorage = JSON.stringify(sessionStorage); } catch(e) { s.sessionStorage = "{}"; }
                try { s.viewport = JSON.stringify({width: window.innerWidth, height: window.innerHeight}); } catch(e) { s.viewport = "{}"; }
                return s;
            }""",
        },
    },
)
raw = self._extract_evaluate_result(combined_result)
state = json.loads(raw)
current_url = state.get("url") or ""
cookies_str = state.get("cookies") or ""
local_storage = state.get("localStorage") or "{}"
session_storage = state.get("sessionStorage") or "{}"
viewport = state.get("viewport") or "{}"
```

### JSON embedding for restore (localStorage/sessionStorage)
```python
# Source: session_state.py restore_state() — after this phase
import json

for key, value in storage_data.items():
    k = json.dumps(key)
    v = json.dumps(value)
    await self.playwright.send_request(
        "tools/call",
        {
            "name": "browser_evaluate",
            "arguments": {
                "function": f"() => localStorage.setItem({k}, {v})",
            },
        },
    )
```

### JSON embedding for restore (cookies)
```python
# Source: session_state.py restore_state() — after this phase
cookie_literal = json.dumps(f"{cookie['name']}={cookie['value']}")
await self.playwright.send_request(
    "tools/call",
    {
        "name": "browser_evaluate",
        "arguments": {
            "function": f"() => document.cookie = {cookie_literal}",
        },
    },
)
```

### Updated test mock for combined capture
```python
# Source: tests/test_phase7_state_capture.py — after this phase
async def mock_send_request(method, params):
    if method != "tools/call":
        return {}
    name = params.get("name", "")
    if name == "browser_evaluate":
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "url": "https://example.com/test",
                    "cookies": "session=abc123; user=john",
                    "localStorage": '{"key1": "value1", "key2": "value2"}',
                    "sessionStorage": '{"tempKey": "tempValue"}',
                    "viewport": '{"width": 1920, "height": 1080}',
                })
            }]
        }
    return {}

# Assertion changes
assert mock_playwright.send_request.call_count == 1  # was 5
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| 5 sequential RPCs for state capture | Single combined RPC | Phase 4 | 4 fewer round-trips over stdio pipe |
| f-string interpolation for JS data | `json.dumps()` embedding | Phase 4 | Eliminates JS injection surface |

**Deprecated/outdated:**
- `value.replace("\\", "\\\\").replace("'", "\\'")` in `restore_state()`: replaced by `json.dumps(value)`.

## Open Questions

1. **Does `restore_state()` need bulk evaluate too (PERF-02 scope)?**
   - What we know: PERF-02 specifies "1 `browser_evaluate` RPC instead of 5" for capture. `restore_state()` issues N RPCs per storage key.
   - What's unclear: Whether the requirement covers restore as well, or only capture.
   - Recommendation: PERF-02 is explicitly about `capture_state()`. Fix only capture for this requirement. Restore stays as-is (per-key calls) but uses the JSON embedding fix for SECR-01.

2. **What happens when `localStorage` is unavailable (about:blank)?**
   - What we know: `SecurityError` is thrown in JS; per-property try/catch handles it.
   - What's unclear: Whether `capture_state()` should return `None` if URL is `null` (navigation not complete).
   - Recommendation: Return partial snapshot if URL is captured, log a warning for null properties. Match existing error-handling behavior (outer try/catch returns `None` for catastrophic failures).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` (asyncio_mode=auto) |
| Quick run command | `uv run pytest tests/test_phase7_state_capture.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PERF-02 | `capture_state()` calls `send_request` exactly once | unit | `uv run pytest tests/test_phase7_state_capture.py::test_capture_state -x` | ✅ (needs update) |
| PERF-02 | Combined function handles one-property failure gracefully | unit | `uv run pytest tests/test_phase7_state_capture.py::test_capture_state_partial_failure -x` | ❌ Wave 0 |
| SECR-01 | `restore_state()` does not use f-string interpolation with user data | unit | `uv run pytest tests/test_phase7_state_capture.py::test_restore_state_injection_safety -x` | ❌ Wave 0 |
| SECR-01 | Values with `'`, `"`, `\`, newlines restore correctly | unit | `uv run pytest tests/test_phase7_state_capture.py::test_restore_state_special_chars -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_phase7_state_capture.py -x`
- **Per wave merge:** `uv run pytest`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_phase7_state_capture.py::test_capture_state_partial_failure` — covers PERF-02 graceful partial state
- [ ] `tests/test_phase7_state_capture.py::test_restore_state_injection_safety` — covers SECR-01 (assert no f-string injection)
- [ ] `tests/test_phase7_state_capture.py::test_restore_state_special_chars` — covers SECR-01 (special chars in keys/values)
- [ ] Update `test_capture_state` and `test_capture_state_empty_cookies`: change `call_count == 5` to `call_count == 1`, update mock to return combined dict

## Sources

### Primary (HIGH confidence)
- `/Users/noomz/.npm/_npx/84539a01c0e4c364/node_modules/playwright/lib/mcp/browser/tools/evaluate.js` — actual `browser_evaluate` schema: `{function, element?, ref?}`, no arg parameter
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/playwright_mcp_proxy/server/session_state.py` — complete current implementation (5 RPCs + f-string interpolation)
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/tests/test_phase7_state_capture.py` — existing test coverage, including `call_count == 5` assertions that need updating
- Python stdlib `json` docs — `json.dumps()` produces valid JSON/JS string literals

### Secondary (MEDIUM confidence)
- REQUIREMENTS.md PERF-02 and SECR-01 requirement text — defines exact success criteria
- ROADMAP.md Phase 4 success criteria — "try/catch per property" and "JSON embedding pattern" both specified there

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — browser_evaluate schema verified from installed source code
- Architecture: HIGH — patterns derived directly from actual evaluate.js implementation
- Pitfalls: HIGH — test assertions and current code examined directly

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable — evaluate tool schema is versioned/pinned)
