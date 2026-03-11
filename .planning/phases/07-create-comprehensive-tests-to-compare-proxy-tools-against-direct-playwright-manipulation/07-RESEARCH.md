# Phase 7: Create Comprehensive Tests to Compare Proxy Tools Against Direct Playwright Manipulation - Research

**Researched:** 2026-03-11
**Domain:** Pytest integration testing, playwright-mcp-proxy HTTP API, comparison test design
**Confidence:** HIGH

## Summary

Phase 7 asks for 3-5 test scenarios that compare using the playwright-mcp-proxy tool stack (create_new_session → browser_navigate → browser_snapshot → get_content) against direct Playwright MCP manipulation (raw JSON-RPC over stdio to `npx @playwright/mcp@latest`). The goal is to verify that the proxy preserves behavior faithfully while demonstrating its value-add features: SQLite persistence, diff-based content delivery, metadata responses, and console log capture.

The existing test infrastructure is pytest with `asyncio_mode = auto` and httpx for HTTP calls. All current unit tests are database/diff-cursor focused. The one integration test file (`test_integration_live.py`) requires a running server but does not use the `@pytest.mark.asyncio` decorator (it relies on `asyncio_mode = auto`). Tests can already reach the proxy server at `http://localhost:34501`.

Direct Playwright MCP access would mean spawning `npx @playwright/mcp@latest` as a subprocess and sending JSON-RPC messages over its stdio pipes — the same pattern already used internally by `PlaywrightManager`. The proxy server itself does this, so the pattern is understood and proven in production code.

**Primary recommendation:** Write all 5 comparison scenarios as pytest integration tests in `tests/test_comparison.py`, using httpx for the proxy path and a thin in-process `DirectPlaywrightClient` helper (subprocess + JSON-RPC stdio) for the direct path. Tests require a running proxy server (`playwright-proxy-server`) and internet access; mark them `@pytest.mark.integration` so they are opt-in, mirroring the existing `test_integration_live.py` convention.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=8.3.0 | Test runner | Already in dev deps |
| pytest-asyncio | >=1.0.0 | Async test support | Already in dev deps; `asyncio_mode = auto` |
| httpx | >=0.28.0 | HTTP client for proxy calls | Already in prod deps |
| asyncio.create_subprocess_exec | stdlib | Spawn direct Playwright process | Same pattern as PlaywrightManager |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest-cov | >=6.0.0 | Coverage reporting | Already in dev deps |
| tempfile / pathlib | stdlib | Isolated DB files per test | Existing pattern in all unit tests |
| unittest.mock | stdlib | Mock HTTP responses in CLI tests | Used in test_ctl.py |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| subprocess stdio JSON-RPC | playwright Python library | playwright-python is a different product; proxy wraps the MCP server subprocess not the Python API, so direct comparison must match the actual communication path |
| Live internet sites | Local HTTP server (pytest-httpserver) | Using real sites (example.com, httpbin.org) is already the established pattern in test_integration_live.py; they are stable enough for comparison tests |

**Installation:**

No new dependencies required. All needed libraries are already in `pyproject.toml`.

## Architecture Patterns

### Recommended Project Structure

New file alongside existing integration test:

```
tests/
├── test_comparison.py        # New: 5 proxy-vs-direct comparison scenarios
├── test_integration_live.py  # Existing: proxy-only live tests
├── test_database.py          # Existing: unit
├── test_diff.py              # Existing: unit
├── test_transaction_batching.py  # Existing: unit
├── test_ctl.py               # Existing: unit (CLI)
├── test_bugs.py              # Existing: unit
└── conftest.py               # Shared fixtures (may need to create)
```

### Pattern 1: Direct Playwright Client Helper

The direct path requires spawning `npx @playwright/mcp@latest` and communicating over stdio JSON-RPC. `PlaywrightManager` already does this. For tests, extract a lightweight standalone version as a pytest fixture or helper class — do NOT import `PlaywrightManager` (it has background tasks and lifecycle complexity); instead write a minimal async context manager.

```python
# tests/test_comparison.py

import asyncio
import json

class DirectPlaywrightClient:
    """Minimal stdio JSON-RPC client for direct Playwright MCP access.
    Mirrors PlaywrightManager.send_request() but without health checks or restart logic.
    """

    def __init__(self):
        self.process = None
        self._msg_id = 0

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            "npx", "@playwright/mcp@0.0.68", "--headless",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await self._initialize()

    async def stop(self):
        if self.process:
            self.process.terminate()
            await self.process.wait()

    async def _initialize(self):
        await self.send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-direct", "version": "0.0.1"},
        })

    async def send(self, method: str, params: dict) -> dict:
        self._msg_id += 1
        msg = json.dumps({
            "jsonrpc": "2.0", "id": self._msg_id,
            "method": method, "params": params,
        }) + "\n"
        self.process.stdin.write(msg.encode())
        await self.process.stdin.drain()
        line = await self.process.stdout.readline()
        response = json.loads(line.decode())
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response.get("result", {})

    async def call_tool(self, name: str, arguments: dict) -> dict:
        return await self.send("tools/call", {"name": name, "arguments": arguments})
```

### Pattern 2: Proxy Client Helper

```python
BASE_URL = "http://localhost:34501"

async def proxy_navigate_and_snapshot(client: httpx.AsyncClient, url: str) -> str:
    """Full proxy workflow: create session, navigate, snapshot, get_content."""
    resp = await client.post("/sessions")
    session_id = resp.json()["session_id"]

    await client.post("/proxy", json={
        "session_id": session_id, "tool": "browser_navigate", "params": {"url": url}
    })
    snap = await client.post("/proxy", json={
        "session_id": session_id, "tool": "browser_snapshot", "params": {}
    })
    ref_id = snap.json()["ref_id"]
    content_resp = await client.get(f"/content/{ref_id}")
    return content_resp.json()["content"]
```

### Pattern 3: Comparison Test Structure

Each scenario runs both paths and asserts they produce equivalent observable outcomes. The comparison is behavioral — "both see the same page content" — not byte-for-byte identical.

```python
@pytest.mark.integration
async def test_scenario_X_compare():
    # Proxy path
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:
        proxy_content = await proxy_navigate_and_snapshot(client, TARGET_URL)

    # Direct path
    direct = DirectPlaywrightClient()
    await direct.start()
    try:
        await direct.call_tool("browser_navigate", {"url": TARGET_URL})
        result = await direct.call_tool("browser_snapshot", {})
        direct_content = result["content"][0]["text"]
    finally:
        await direct.stop()

    # Behavioral equivalence: both see same landmark content
    assert "Expected Heading" in proxy_content
    assert "Expected Heading" in direct_content
```

### Anti-Patterns to Avoid

- **Sharing a single Playwright subprocess between proxy and direct paths:** The proxy server already owns a subprocess on port 34501; tests must spawn a SECOND instance for the direct path. These will use different browser contexts.
- **Byte-exact content comparison:** Accessibility tree output can differ slightly between runs (timestamps, dynamic IDs). Assert on stable landmark content.
- **Sequential test ordering dependencies:** Each test must create its own session and manage its own direct client lifecycle.
- **Importing PlaywrightManager in tests:** It has asyncio background tasks that conflict with test teardown; use the thin `DirectPlaywrightClient` helper above.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP testing | Custom TCP client | httpx.AsyncClient | Already used everywhere; handles timeout, redirects, JSON |
| Subprocess JSON-RPC | Full MCP client library | asyncio.create_subprocess_exec + json | PlaywrightManager already proves this is sufficient; no deps needed |
| Test isolation | Manual DB cleanup | `tempfile.NamedTemporaryFile` fixture | Existing pattern across all unit tests |
| Async test fixtures | Manual event loop management | pytest-asyncio `asyncio_mode = auto` | Already configured in pyproject.toml |

## 5 Comparison Scenarios

These are the concrete scenarios to implement. They progress from trivial to meaningfully complex.

### Scenario 1: Simple Page Navigation and Content Verification

**What it tests:** Both paths can navigate to a stable page and see the same landmark content.
**URL:** `https://example.com`
**Proxy value demonstrated:** Metadata response + ref_id workflow; first `get_content` returns full snapshot.
**Direct path:** `browser_navigate` + `browser_snapshot` — raw accessibility tree returned inline.
**Assertion:** Both contain "Example Domain".

### Scenario 2: Diff-Based Content Retrieval (Proxy-Unique Feature)

**What it tests:** The proxy's hash-based diff cursor — second `get_content` on the same ref_id returns empty (unchanged), while the direct path always returns full content.
**URL:** `https://example.com`
**Proxy value demonstrated:** Token savings through diff suppression.
**Direct path:** Two sequential `browser_snapshot` calls both return full content.
**Assertion:**
- Proxy first read: non-empty.
- Proxy second read (same ref_id): empty string.
- Direct second snapshot: non-empty.
- This is the clearest behavioral difference between the two approaches.

### Scenario 3: Multi-Page Navigation

**What it tests:** Navigate to two different sites in sequence; verify each snapshot reflects the correct page.
**URLs:** `https://example.com` then `https://httpbin.org`
**Proxy value demonstrated:** All interactions logged to SQLite with unique ref_ids; historical content retrievable.
**Direct path:** Sequential navigate + snapshot; content only available in current call.
**Assertion:** Proxy content[0] contains "Example Domain"; content[1] contains "httpbin". Same for direct.

### Scenario 4: Content Search / Filtering (Proxy-Unique Feature)

**What it tests:** Proxy's `search_for` parameter filters snapshot to matching lines; direct path returns full accessibility tree and caller must grep manually.
**URL:** `https://example.com`
**Proxy value demonstrated:** `get_content(ref_id, search_for="Example Domain")` returns only matching lines — smaller payload.
**Direct path:** Full snapshot; manually filter with Python `in` check.
**Assertion:**
- Proxy filtered result length < proxy full result length.
- Both still contain "Example Domain".
- Direct path has no built-in filtering (asserted by confirming full content is returned).

### Scenario 5: Error Handling — Invalid URL

**What it tests:** Both paths handle a navigation error gracefully.
**URL:** `https://this-domain-does-not-exist-at-all-12345.invalid`
**Proxy value demonstrated:** Errors are persisted in SQLite with ref_id; proxy returns structured error response with `status: error`.
**Direct path:** `browser_navigate` returns an MCP error or `isError: true` in the result.
**Assertion:**
- Proxy: response `status == "error"` and `ref_id` is present (audit trail preserved even on error).
- Direct: either raises RuntimeError (MCP error in response) or returns result with `isError: true`.
- Both fail gracefully without crashing the test.

## Common Pitfalls

### Pitfall 1: Two Playwright Processes Contending for the Same Browser Profile

**What goes wrong:** The direct client spawns a second `npx @playwright/mcp` process. By default both may try to use the same Chromium user data directory, causing startup failures or intermittent test failures.
**Why it happens:** `@playwright/mcp` defaults to a shared profile path.
**How to avoid:** Pass `--headless` to the direct client (tests are headless anyway). If contention persists, consider running the proxy server with `PLAYWRIGHT_PROXY_PLAYWRIGHT_BROWSER=firefox` so the two processes use different browser binaries.
**Warning signs:** "browser already running" errors in direct client stderr.

### Pitfall 2: Snapshot Content Differs Between Two Browser Instances

**What goes wrong:** The proxy and direct path may see slightly different accessibility trees for the same URL (different browser state, timing, browser version).
**Why it happens:** Two separate browser processes with independent state and no shared cookies/storage.
**How to avoid:** Assert only on stable landmark content (heading text, page title). Never assert on ref attributes (e.g., `[ref=e6]`) or full snapshot equality.

### Pitfall 3: Direct Client Blocks Indefinitely on Slow Network

**What goes wrong:** `readline()` on the subprocess stdout hangs if Playwright MCP does not respond.
**Why it happens:** No timeout on asyncio readline by default.
**How to avoid:** Wrap reads with `asyncio.wait_for(..., timeout=30.0)`. The existing `PlaywrightManager.send_request` uses a lock but no per-read timeout on the actual readline — the test helper should add one.

### Pitfall 4: Tests Pass Locally but Fail in CI Without a Server

**What goes wrong:** `test_integration_live.py` already requires a running server. Comparison tests have the same requirement PLUS a second Node.js process.
**Why it happens:** These are live integration tests, not unit tests.
**How to avoid:** Mark with `@pytest.mark.integration`. Document in test file docstring: "Requires `playwright-proxy-server` running on localhost:34501 and `npx` available." Mirror the convention already in `test_integration_live.py`.

### Pitfall 5: conftest.py Fixture Scope Conflict

**What goes wrong:** If a shared `db` fixture at session scope is added to conftest.py, it may interfere with per-test temp DB teardown.
**Why it happens:** asyncio_mode=auto + session-scoped async fixtures have subtle teardown ordering.
**How to avoid:** Keep comparison test fixtures function-scoped. Do not add a global `db` fixture to conftest.py unless all unit tests are confirmed compatible.

## Code Examples

### Direct Playwright Client with Timeout Guard

```python
# Source: PlaywrightManager._read_line_chunked pattern (playwright_mcp_proxy/server/playwright_manager.py)

async def _readline_with_timeout(stream, timeout=30.0) -> bytes:
    """Read a line from stream with timeout to prevent indefinite blocking."""
    try:
        return await asyncio.wait_for(stream.readline(), timeout=timeout)
    except asyncio.TimeoutError:
        raise RuntimeError(f"Direct Playwright client timed out waiting for response")
```

### Pytest Fixture for Direct Client

```python
@pytest.fixture
async def direct_client():
    """Spawn a direct Playwright MCP subprocess for comparison."""
    client = DirectPlaywrightClient()
    await client.start()
    yield client
    await client.stop()
```

### Scenario 2 (Diff) Test Skeleton

```python
@pytest.mark.integration
async def test_diff_proxy_suppresses_unchanged_content_direct_always_returns():
    """
    Proxy second read returns empty (diff cursor, no changes).
    Direct second snapshot always returns full content.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as http:
        sid = (await http.post("/sessions")).json()["session_id"]
        await http.post("/proxy", json={
            "session_id": sid, "tool": "browser_navigate",
            "params": {"url": "https://example.com"}
        })
        snap = await http.post("/proxy", json={
            "session_id": sid, "tool": "browser_snapshot", "params": {}
        })
        ref_id = snap.json()["ref_id"]

        first = (await http.get(f"/content/{ref_id}")).json()["content"]
        second = (await http.get(f"/content/{ref_id}")).json()["content"]

        assert len(first) > 0
        assert second == ""   # diff suppression — proxy unique

    direct = DirectPlaywrightClient()
    await direct.start()
    try:
        await direct.call_tool("browser_navigate", {"url": "https://example.com"})
        r1 = await direct.call_tool("browser_snapshot", {})
        r2 = await direct.call_tool("browser_snapshot", {})
        c1 = r1["content"][0]["text"]
        c2 = r2["content"][0]["text"]
        assert len(c1) > 0
        assert len(c2) > 0   # direct always returns full content
    finally:
        await direct.stop()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| @pytest.mark.asyncio decorator on each test | asyncio_mode = auto in pyproject.toml | Phase 1 (pytest-asyncio >=1.0.0) | No per-test decorator needed |
| str() for params serialization | json.dumps() | Phase 2 (BUGF-01) | DB params are valid JSON |
| 3+ commits per proxy request | 2-commit boundary (pre-RPC + post-RPC batch) | Phase 3 | Tests can verify request record persists even on Playwright error |
| @playwright/mcp@latest | @playwright/mcp@0.0.68 | Phase 1 (DEPS-03) | Direct client in tests must use same pinned version |

**Deprecated/outdated:**
- `@pytest.mark.asyncio` on individual tests: pyproject.toml already sets `asyncio_mode = "auto"` — do not add this decorator.

## Open Questions

1. **Browser profile isolation for the direct client**
   - What we know: Two playwright MCP processes may contend for the same user data dir.
   - What's unclear: Whether `--headless` is sufficient to avoid the conflict or if `--no-sandbox` / `--user-data-dir` flags are needed.
   - Recommendation: Start with `--headless` only; if tests are flaky, add a `--user-data-dir=$(mktemp -d)` flag to the direct client spawn.

2. **Whether httpbin.org forms page is stable enough for Scenario 3**
   - What we know: `test_integration_live.py` already uses it and it works.
   - What's unclear: Form POST interactions (Scenario 4 could use it for a type+submit comparison) may be harder to assert on.
   - Recommendation: Scenario 3 uses httpbin.org for navigation only (no form interaction), which is proven stable.

3. **MCP version of `browser_snapshot` return structure in direct path**
   - What we know: `PlaywrightManager.send_request` returns `response.get("result", {})`. For `tools/call`, the result has `{"content": [{"type": "text", "text": "..."}]}`.
   - What's unclear: Whether `@playwright/mcp@0.0.68` uses exactly this structure for all tools.
   - Recommendation: Add an assertion on `result["content"][0]["type"] == "text"` in the direct path helper to fail fast with a clear error if the structure changes.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.3.0+ with pytest-asyncio 1.0.0+ |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_comparison.py -v -m integration` |
| Full suite command | `uv run pytest -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| (no formal req ID) | Scenario 1: navigate + snapshot equivalence | integration | `uv run pytest tests/test_comparison.py::test_scenario1_simple_navigation -x` | Wave 0 |
| (no formal req ID) | Scenario 2: diff suppresses unchanged content | integration | `uv run pytest tests/test_comparison.py::test_scenario2_diff_behavior -x` | Wave 0 |
| (no formal req ID) | Scenario 3: multi-page navigation equivalence | integration | `uv run pytest tests/test_comparison.py::test_scenario3_multi_page_navigation -x` | Wave 0 |
| (no formal req ID) | Scenario 4: content search proxy-unique feature | integration | `uv run pytest tests/test_comparison.py::test_scenario4_content_search -x` | Wave 0 |
| (no formal req ID) | Scenario 5: error handling both paths | integration | `uv run pytest tests/test_comparison.py::test_scenario5_error_handling -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -v --ignore=tests/test_comparison.py --ignore=tests/test_integration_live.py` (unit tests only — no server required)
- **Per wave merge:** `uv run pytest tests/ -v -m "not integration"` (excludes live tests)
- **Phase gate:** `uv run pytest tests/test_comparison.py tests/test_integration_live.py -v` (full integration suite; requires running server)

### Wave 0 Gaps

- [ ] `tests/test_comparison.py` — new file covering all 5 comparison scenarios
- [ ] `DirectPlaywrightClient` helper class — inline in test_comparison.py or extracted to `tests/helpers/direct_client.py`
- [ ] Shared proxy helper functions (`proxy_navigate_and_snapshot`, `_create_session`) — can be module-level functions in test_comparison.py or moved to `tests/conftest.py` if shared with test_integration_live.py

## Sources

### Primary (HIGH confidence)

- `playwright_mcp_proxy/server/playwright_manager.py` — send_request(), _read_line_chunked(), subprocess spawn pattern
- `tests/test_integration_live.py` — established conventions for live integration tests (httpx, BASE_URL, TIMEOUT, async helpers)
- `pyproject.toml` — pinned dependency versions, pytest asyncio_mode=auto
- `playwright_mcp_proxy/client/mcp_server.py` — TOOLS list (9 tools), handle_tool_call() shows the response format
- `playwright_mcp_proxy/server/app.py` — proxy endpoint logic, content diff algorithm, console log handling

### Secondary (MEDIUM confidence)

- `tests/test_ctl.py` — demonstrates unittest.mock usage pattern for HTTP mocking if needed
- `tests/test_transaction_batching.py` — demonstrates fixture composition pattern (db_with_session)
- `PHASE7_DESIGN.md` / `PHASE7_STATUS.md` — these are an older "restart recovery" Phase 7 design from before the roadmap was extended; the current Phase 7 in the roadmap is the comparison tests phase

### Tertiary (LOW confidence)

- None — all findings are from project source code directly

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new libraries needed; existing deps confirmed
- Architecture: HIGH — DirectPlaywrightClient pattern is a simplification of PlaywrightManager which is already production code
- Pitfalls: HIGH — browser profile contention is a known issue with multiple playwright processes; diff behavior is documented and tested
- Scenarios: HIGH — scenarios derived directly from the proxy's documented value-add features (diff, persistence, search, metadata)

**Research date:** 2026-03-11
**Valid until:** 2026-04-11 (stable dependencies; only risk is httpbin.org availability changes)
