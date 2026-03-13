# Phase 8: Add New Perf Comparison Results Between Claude in Chrome - Research

**Researched:** 2026-03-12
**Domain:** Test extension, claude-in-chrome MCP tools, performance benchmarking
**Confidence:** HIGH

## Summary

Phase 8 extends the Phase 7 comparison test framework by adding a third path: **Claude in Chrome** (`mcp__claude-in-chrome__*` tools). Phase 7 already built `tests/test_comparison.py` with `DirectPlaywrightClient` (direct Playwright MCP subprocess) and proxy HTTP API comparisons. This phase adds scenarios that run the same browser automation tasks via `mcp__claude-in-chrome` tools and reports performance metrics (latency, payload size, estimated tokens) alongside the existing proxy and direct paths.

The `mcp__claude-in-chrome` MCP server is a Chrome browser extension that exposes the currently open Chrome browser to Claude Code. It provides tools: `tabs_context_mcp`, `tabs_create_mcp`, `navigate`, `computer` (screenshot/click), `read_page` (accessibility tree), `find`, `form_input`, `get_page_text`. It is already in use in another project (`ibudget-uat`) where it serves as the primary browser interaction method for test generation workflows.

The key measurement difference: claude-in-chrome operates on the user's actual Chrome browser (persistent, tab-aware), while playwright-proxy and direct Playwright spawn headless Chromium subprocesses. This makes latency and payload characteristics distinct enough to produce meaningful benchmarking data.

**Primary recommendation:** Add a new test file `tests/test_chrome_comparison.py` (or extend `tests/test_comparison.py` with additional scenarios) that runs the same navigation scenarios via claude-in-chrome tools, collects `Measurement` objects using the identical `ScenarioMetrics` dataclass pattern already established, and produces a unified performance table showing all three paths side-by-side. Since claude-in-chrome is a Claude Code MCP tool (not callable from pytest), the "chrome path" measurements must be executed as direct Claude Code interactions and recorded/appended to the existing metrics output format.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=8.3.0 | Test runner | Already in dev deps |
| pytest-asyncio | >=1.0.0 | Async test support | `asyncio_mode = auto` already configured |
| httpx | >=0.28.0 | HTTP client for proxy calls | Already in prod deps |
| mcp__claude-in-chrome__* | N/A (MCP server) | Chrome browser automation tools | Available in user's Claude Code environment |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| time.perf_counter | stdlib | Latency measurement | Same pattern as Phase 7 `Measurement` dataclass |
| dataclasses | stdlib | Metrics collection | `ScenarioMetrics` and `Measurement` already defined in test_comparison.py |
| json | stdlib | Payload size calculation | Already used in test_comparison.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate test file | Extend test_comparison.py with more scenarios | Extending adds chrome scenarios inline; separate file is cleaner and doesn't risk breaking existing passing tests |
| pytest test functions for chrome path | Standalone Python script that calls claude-in-chrome | claude-in-chrome tools are MCP tools invoked by Claude, not callable from Python subprocess — the measurements must be captured differently (see Architecture Patterns) |

**Installation:**

No new Python dependencies required. `mcp__claude-in-chrome` is a Claude Code MCP server, not a Python package.

## Architecture Patterns

### The Core Challenge: MCP Tools Are Not Subprocess-Callable

The critical design constraint is that `mcp__claude-in-chrome__*` tools are MCP protocol tools invoked by Claude Code directly — they cannot be called from a Python test process. This means the Phase 7 pattern (spawning subprocesses and communicating via stdio) does not apply to the chrome path.

Three viable approaches, ranked by simplicity:

**Approach A (Recommended): Claude-executed chrome measurements + results fixture**

Claude Code manually executes the chrome-path operations (navigate, read_page, etc.), records timing and payload sizes in a Python data structure, then writes those measurements to a JSON fixture file. A lightweight pytest test reads the fixture and incorporates the chrome measurements into the final performance table.

```
claude navigates with chrome tools → records timing/bytes → writes chrome_measurements.json
pytest test_chrome_comparison.py reads chrome_measurements.json → generates merged report
```

This is the cleanest separation: chrome measurements come from actual Claude Code execution (where the tools exist), and the report generation is pure Python.

**Approach B: Standalone script that prints the chrome comparison table**

A standalone Python script `scripts/run_chrome_comparison.py` that accepts pre-measured chrome metrics as command-line arguments or reads from a JSON file, combines with proxy/direct measurements from a saved run, and prints the merged performance table. No pytest involvement.

**Approach C: Document-only results file**

Claude Code runs chrome operations, measures timing manually, and writes results to `tests/chrome_comparison_results.md` as a markdown table. No code automation needed. Simplest to implement, least reusable.

**Recommended: Approach A** — keeps the metrics format consistent with Phase 7, produces a machine-readable output, and allows future reruns.

### Recommended Project Structure

```
tests/
├── test_comparison.py            # Existing: proxy vs direct (7 scenarios with perf table)
├── test_chrome_comparison.py     # New: loads chrome measurements, generates merged table
├── chrome_measurements.json      # Generated by Claude during chrome path execution
└── fixtures/                     # Not needed (no new pytest fixtures required)

scripts/
└── run_chrome_comparison.py      # Optional: standalone merged report generator
```

### Pattern 1: Chrome Measurements JSON Format

Claude Code executes chrome operations and writes this file:

```json
{
  "generated_at": "2026-03-12T10:00:00Z",
  "scenarios": [
    {
      "name": "Simple Navigation (example.com)",
      "measurements": [
        {
          "label": "navigate",
          "path": "chrome",
          "elapsed_ms": 1250.0,
          "payload_bytes": 0,
          "estimated_tokens": 0
        },
        {
          "label": "read_page (full snapshot)",
          "path": "chrome",
          "elapsed_ms": 340.0,
          "payload_bytes": 4200,
          "estimated_tokens": 1050
        }
      ],
      "notes": [
        "chrome: operates on existing Chrome tab, no subprocess spawn overhead"
      ]
    }
  ]
}
```

### Pattern 2: test_chrome_comparison.py Structure

```python
# tests/test_chrome_comparison.py
# Source: extends pattern from tests/test_comparison.py

import json
import pathlib
import pytest
from tests.test_comparison import ScenarioMetrics, Measurement, _format_table, _estimate_tokens

CHROME_MEASUREMENTS_PATH = pathlib.Path(__file__).parent / "chrome_measurements.json"

@pytest.mark.chrome_comparison
def test_load_and_report_chrome_comparison():
    """Load pre-recorded chrome path measurements and generate merged report."""
    if not CHROME_MEASUREMENTS_PATH.exists():
        pytest.skip("chrome_measurements.json not found — run chrome path measurement first")

    data = json.loads(CHROME_MEASUREMENTS_PATH.read_text())
    # ... generate merged table
```

### Pattern 3: claude-in-chrome Tool Invocation Pattern

When Claude Code runs the chrome path measurements, the tool call sequence mirrors the proxy pattern:

```
# Navigate to URL
mcp__claude-in-chrome__navigate(url="https://example.com")
  → Records: elapsed_ms, no payload (navigate returns void)

# Get accessibility tree (equivalent to browser_snapshot + get_content)
mcp__claude-in-chrome__read_page()
  → Records: elapsed_ms, payload_bytes=len(json.dumps(result)), estimated_tokens

# Take screenshot (optional, for visual verification)
mcp__claude-in-chrome__computer(action="screenshot")
  → Records: elapsed_ms, payload_bytes (image data size)
```

### Anti-Patterns to Avoid

- **Trying to call mcp__claude-in-chrome from Python subprocess:** These are MCP tools, not CLI commands. There is no `npx @claude-in-chrome/mcp` equivalent.
- **Mixing chrome tab state between scenarios:** chrome-in-chrome operates on an existing Chrome instance. Navigate to a specific URL before each scenario to ensure a clean starting state.
- **Assuming chrome produces the same accessibility tree format as Playwright MCP:** `read_page` output from claude-in-chrome may differ structurally from Playwright MCP's `browser_snapshot` output. Do not assert identical content — assert the same landmark text is present.
- **Hardcoding element refs across paths:** Playwright MCP uses `[ref=e47]`-style references; claude-in-chrome uses description-based element targeting. The two systems are not interchangeable.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timing measurements | Custom timer class | `time.perf_counter()` with `Measurement` dataclass | Already established in test_comparison.py |
| Token estimation | Custom tokenizer | `_estimate_tokens()` from test_comparison.py (~4 chars/token) | Consistent across all paths; exact tokenization irrelevant for comparison |
| Report formatting | Custom markdown generator | `_format_table()` from test_comparison.py | Consistent ASCII table format already proven |
| Chrome accessibility tree parsing | Custom parser | Use `read_page` output directly; measure `len(json.dumps(result))` | No parsing needed for metrics collection |

**Key insight:** The Phase 7 `Measurement`, `ScenarioMetrics`, and `_format_table` infrastructure is exactly what Phase 8 needs. Import from `test_comparison.py` rather than duplicating.

## Common Pitfalls

### Pitfall 1: chrome-in-chrome Requires Connected Browser
**What goes wrong:** `mcp__claude-in-chrome__tabs_context_mcp` returns an error or empty result when Chrome isn't open or the extension isn't connected.
**Why it happens:** Unlike Playwright which spawns its own subprocess, claude-in-chrome connects to an already-running Chrome instance via the Chrome extension protocol.
**How to avoid:** Check `tabs_context_mcp` first. If no tabs returned, stop and report "Chrome browser with extension not connected."
**Warning signs:** Empty tabs list, connection refused errors from the extension.

### Pitfall 2: Stale Tab State
**What goes wrong:** Chrome already has the target URL open from a previous run; the navigate call returns immediately (no actual load), producing unrealistically low elapsed times.
**Why it happens:** Chrome reuses existing tabs if the URL matches; Playwright always starts fresh.
**How to avoid:** Use `tabs_create_mcp` to create a fresh tab for each scenario, then navigate. Or navigate to `about:blank` first to clear tab state.
**Warning signs:** Navigate elapsed_ms < 100ms for a remote URL (genuine network loads take 300ms+).

### Pitfall 3: read_page Returns Different Structure Than Playwright browser_snapshot
**What goes wrong:** Code tries to assert `"Example Domain" in result["content"][0]["text"]` (Playwright MCP format) on claude-in-chrome's `read_page` output.
**Why it happens:** The two tools return different JSON shapes.
**How to avoid:** `read_page` returns the accessibility tree as a string directly (or a dict — verify by calling it once and inspecting). Do not assume Playwright MCP's `content[0].text` structure.
**Warning signs:** `KeyError` or `TypeError` when accessing the result.

### Pitfall 4: Screenshot Payloads Dominate Metrics
**What goes wrong:** Including `computer(action="screenshot")` measurements inflates the payload size comparison because screenshots are binary image data (100KB+), dwarfing text snapshots.
**Why it happens:** Screenshots are fundamentally different data from accessibility trees.
**How to avoid:** Report screenshot metrics separately as an "optional visual verification" row. Don't average screenshot payload with text payload rows.
**Warning signs:** Chrome path showing 10x higher payload_bytes than proxy/direct on the same page.

### Pitfall 5: Comparison Fairness (Tab Reuse vs Fresh Process)
**What goes wrong:** Chrome path shows faster navigation because Chrome is already running with warm caches, making comparison unfair.
**Why it happens:** Playwright always spawns a fresh process; Chrome reuses cached resources.
**How to avoid:** Explicitly note in the comparison table footer: "Chrome path uses existing Chrome instance (warm cache); Playwright paths use fresh headless Chromium (cold start)." This context makes the numbers meaningful rather than misleading.
**Warning signs:** Chrome navigate times consistently 3-5x faster than Playwright paths.

## Code Examples

Verified patterns from existing project sources:

### Chrome Tool Invocation (from ibudget gentest SKILL.md)
```python
# Source: /Users/noomz/Projects/Opendream/ibudget/ibudget-uat/.claude/skills/_shared/reference.md
# These are MCP tool calls executed by Claude Code, not Python functions

# Get current tab info
tabs = mcp__claude-in-chrome__tabs_context_mcp()

# Create a new tab
mcp__claude-in-chrome__tabs_create_mcp()

# Navigate to URL
mcp__claude-in-chrome__navigate(url="https://example.com")

# Take screenshot
mcp__claude-in-chrome__computer(action="screenshot")

# Read accessibility tree
result = mcp__claude-in-chrome__read_page()

# Find element by description
mcp__claude-in-chrome__find(description="Submit button")

# Click element
mcp__claude-in-chrome__computer(action="left_click", coordinate=[x, y])

# Type into form field
mcp__claude-in-chrome__form_input(selector="input[type=search]", value="playwright")

# Get page text
text = mcp__claude-in-chrome__get_page_text()
```

### Measurement Capture Pattern (extends test_comparison.py)
```python
# Source: tests/test_comparison.py (Phase 7, existing)
import time
import json
from dataclasses import dataclass, field

@dataclass
class Measurement:
    label: str
    path: str  # "proxy", "direct", or "chrome"
    elapsed_ms: float = 0.0
    payload_bytes: int = 0
    estimated_tokens: int = 0

# When Claude executes chrome path:
t0 = time.perf_counter()
result = mcp__claude-in-chrome__read_page()
elapsed_ms = (time.perf_counter() - t0) * 1000
payload_bytes = len(json.dumps(result))
estimated_tokens = max(1, payload_bytes // 4)

m = Measurement(
    label="read_page (accessibility tree)",
    path="chrome",
    elapsed_ms=elapsed_ms,
    payload_bytes=payload_bytes,
    estimated_tokens=estimated_tokens,
)
```

### Chrome Measurements JSON Writer (standalone Python)
```python
# scripts/record_chrome_measurements.py
# Claude Code executes this after running chrome path manually

import json
import pathlib
from datetime import datetime, timezone

measurements = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "scenarios": [
        {
            "name": "Simple Navigation (example.com)",
            "measurements": [
                # Populated by Claude after executing chrome tools
            ],
            "notes": []
        }
    ]
}

output = pathlib.Path("tests/chrome_measurements.json")
output.write_text(json.dumps(measurements, indent=2))
print(f"Written: {output}")
```

### test_chrome_comparison.py Loading Pattern
```python
# tests/test_chrome_comparison.py
import json
import pathlib
import pytest

CHROME_MEASUREMENTS_PATH = pathlib.Path(__file__).parent / "chrome_measurements.json"

@pytest.mark.chrome_comparison
def test_chrome_comparison_report():
    if not CHROME_MEASUREMENTS_PATH.exists():
        pytest.skip("chrome_measurements.json not available — execute chrome path first")
    data = json.loads(CHROME_MEASUREMENTS_PATH.read_text())
    # Merge with proxy/direct measurements and print table
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 7: proxy vs direct only | Phase 8: proxy vs direct vs chrome | Phase 8 | Three-way comparison shows real-world trade-offs |
| Scenarios 1-5: basic behavioral tests | Scenarios 6-7: complex pages (Google, YouTube) already added | Phase 7 (already in test_comparison.py) | Complex page metrics already collected for proxy/direct |
| Manual timing | `time.perf_counter()` in Measurement dataclass | Phase 7 | Consistent sub-millisecond timing across all paths |

**Already done in Phase 7 (do NOT redo):**
- Scenarios 1-5 covering basic behavioral equivalence (CMP-01 through CMP-05)
- Scenarios 6-7 covering Google Search and YouTube (already in test_comparison.py with full metrics)
- `Measurement`, `ScenarioMetrics`, `_format_table`, `_estimate_tokens` infrastructure
- `print_comparison_report` session-scoped fixture
- `DirectPlaywrightClient` for direct Playwright subprocess path

## Open Questions

1. **Does read_page return a dict or string?**
   - What we know: The ibudget skill reference shows `read_page` but doesn't specify return type. The Playwright MCP analog (`browser_snapshot` → `get_content`) returns a string.
   - What's unclear: Whether `read_page` returns `{"content": "...text..."}` (dict) or the accessibility tree string directly.
   - Recommendation: Call `read_page` once during chrome path execution and inspect the raw result before writing measurement code. Adjust `payload_bytes = len(json.dumps(result))` accordingly.

2. **Which scenarios should have a chrome path?**
   - What we know: Chrome path can do navigate, read_page (equivalent to browser_snapshot+get_content), form_input, find+click.
   - What's unclear: Whether to add chrome as a third path to all 7 existing scenarios or only to a subset.
   - Recommendation: Start with Scenarios 1 (simple navigation) and 6 (Google Search) since these are the most meaningful for token comparison. Scenario 2 (diff behavior) has no chrome equivalent since chrome doesn't have diff suppression.

3. **Does claude-in-chrome support headless mode or require visible Chrome?**
   - What we know: It connects to an existing Chrome instance via the extension — Chrome must be running.
   - What's unclear: Whether this is compatible with CI/automated test environments.
   - Recommendation: Mark chrome comparison tests as `@pytest.mark.chrome_comparison` (a new marker) so they are always opt-in and not run in standard `pytest` invocations.

4. **Is there overlap between Scenario 7 (YouTube) and a chrome path YouTube scenario?**
   - What we know: Phase 7 already has `test_scenario7_youtube_search` for proxy and direct paths.
   - What's unclear: Whether the YouTube scenario should get a chrome path variant.
   - Recommendation: Include YouTube as a chrome path scenario since it's the most resource-intensive and will show the most dramatic token difference between paths.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.3.0+ with pytest-asyncio 1.0.0+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_chrome_comparison.py -v -m chrome_comparison` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements → Test Map

No formal requirement IDs assigned to Phase 8. The implicit requirements are:

| Behavior | Test Type | Automated Command |
|----------|-----------|-------------------|
| chrome_measurements.json loads without error | unit | `uv run pytest tests/test_chrome_comparison.py -v` |
| Merged comparison table prints with all three paths | integration | `uv run pytest tests/ -v -m chrome_comparison -s` |
| Chrome path navigate+read_page latency recorded | manual (Claude executes) | Claude executes chrome tools, writes measurements JSON |

### Sampling Rate
- **Per task commit:** `uv run python -c "import ast; ast.parse(open('tests/test_chrome_comparison.py').read()); print('syntax ok')"`
- **Per wave merge:** `uv run pytest tests/test_chrome_comparison.py -v`
- **Phase gate:** Chrome measurements JSON exists and merged table prints before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/chrome_measurements.json` — does not exist yet; Claude must execute chrome path to generate it
- [ ] `tests/test_chrome_comparison.py` — new file, covers chrome path loading and report generation
- [ ] New pytest marker: `chrome_comparison` must be added to `pyproject.toml` markers list

*(No framework install needed — existing pytest infrastructure covers all requirements)*

## Sources

### Primary (HIGH confidence)
- `tests/test_comparison.py` (Phase 7, local) — `Measurement`, `ScenarioMetrics`, `_format_table`, `_estimate_tokens`, 7 scenarios already implemented
- `/Users/noomz/Projects/Opendream/ibudget/ibudget-uat/.claude/skills/_shared/reference.md` — authoritative claude-in-chrome tool list and usage patterns
- `/Users/noomz/Projects/Opendream/ibudget/ibudget-uat/.claude/skills/gentest/SKILL.md` — production usage of `mcp__claude-in-chrome__*` tools in a real workflow
- `pyproject.toml` — pytest configuration, asyncio_mode=auto, existing markers

### Secondary (MEDIUM confidence)
- `.planning/phases/07-*/07-01-PLAN.md` — Phase 7 design decisions, `DirectPlaywrightClient` pattern
- `.planning/phases/07-*/07-VERIFICATION.md` — confirmed Phase 7 artifacts and their line counts

### Tertiary (LOW confidence)
- Inference about `read_page` return type based on ibudget usage patterns — not directly verified by reading the chrome extension source

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all Python deps already in project; chrome-in-chrome tools verified in ibudget project
- Architecture: HIGH — phase 7 infrastructure is directly reusable; three-path design is straightforward extension
- Chrome tool behavior: MEDIUM — tool names and basic usage verified in ibudget, return type of `read_page` not inspected directly
- Pitfalls: HIGH — stale tab state and format difference pitfalls confirmed by ibudget SKILL.md patterns

**Research date:** 2026-03-12
**Valid until:** 2026-04-12 (stable domain; chrome-in-chrome tools unlikely to change)
