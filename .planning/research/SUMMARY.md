# Project Research Summary

**Project:** Playwright MCP Proxy -- Modernization & Tech Debt
**Domain:** Python async MCP proxy -- dependency updates and bug fixes
**Researched:** 2026-03-09
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a tech debt cleanup and modernization pass on an existing, working Python MCP proxy system. The project has accumulated dependency drift (minimum versions far below resolved versions, one missing explicit dependency), several data-integrity bugs (params stored as Python repr instead of JSON, hardcoded error counts, broken console log filtering), a JS injection surface in session state restoration, and performance waste (multiple DB commits per request, multiple subprocess RPCs where one suffices). None of these are architectural problems -- the two-component design (MCP Client + HTTP Server + Playwright subprocess) is sound and unchanged by this work.

The recommended approach is to work in four phases: first fix all dependency declarations and version floors, then fix all low-complexity bugs (6 independent items, each a one-line to few-line change), then add transaction batching to the database layer, then consolidate the evaluate RPCs and fix the JS injection surface together. This ordering respects dependency chains, delivers quick wins early, and groups related changes to minimize context-switching.

The primary risks are: (1) transaction batching that accidentally erases the request audit trail by grouping pre-RPC and post-RPC writes together, (2) the MCP SDK's rapid evolution breaking the client protocol on upgrade, and (3) the JS injection fix relying on Playwright MCP evaluate arg-passing semantics that may not exist. All three have concrete mitigations identified in the research. The overall effort is estimated at 5-7 hours of implementation.

## Key Findings

### Recommended Stack

The stack is stable and well-chosen. No technology replacements are needed. The main actions are bumping minimum version floors to match reality and adding one missing dependency.

**Critical changes:**
- **pydantic-settings**: Missing from pyproject.toml but imported in config.py. Works today only because `mcp` pulls it transitively. Must be added explicitly.
- **mcp SDK**: Floor at >=1.0.0 but resolved to 1.18.0. Bump to >=1.15.0 and add <2.0.0 ceiling to prevent future breakage.
- **pytest-asyncio**: Major version jump from 0.x to 1.x. Project config already uses `asyncio_mode = "auto"` so upgrade should be smooth, but tests must be verified.
- **@playwright/mcp**: Unpinned (`@latest`). Must pin to the exact version currently working.

**Low-risk bumps:** FastAPI >=0.119.0, uvicorn >=0.34.0, pydantic >=2.10.0, httpx >=0.28.0, ruff >=0.9.0. All backward-compatible within this project's usage.

### Expected Features

**Must fix (table stakes -- these are bugs):**
- `json.dumps(params)` instead of `str(params)` -- stored params are currently undeserializable
- Console error count returns actual count instead of hardcoded 0
- Console log level filtering works in the blob fallback path
- `pydantic-settings` declared as explicit dependency
- `@playwright/mcp` version pinned
- Debug logging removed from production hot path in operations.py

**Should fix (differentiators -- correctness and performance):**
- Database transaction batching (3+ commits per request reduced to 1)
- Combine 5 sequential evaluate RPCs into 1 for state capture
- Fix JS injection in state restoration via JSON data embedding
- Batch restore operations (N+M+K RPCs reduced to 2-3)

**Defer (anti-features for this milestone):**
- Authentication, rate limiting (single-user localhost tool)
- Comprehensive test coverage (separate milestone)
- Database migration framework
- Console log normalization on write path
- Global state refactoring in app.py

### Architecture Approach

The architecture is unchanged. All fixes live within the HTTP Server component's internal layers: `app.py` (endpoint handlers), `Database` (operations.py), and `SessionStateManager` (session_state.py). No changes to the MCP Client, PlaywrightManager interface, or data models. The transaction context manager is the only new abstraction -- it wraps existing write methods to defer commits.

**Key data flow change:** The proxy endpoint should move the Playwright RPC before DB writes, then batch post-RPC writes (create_response + update_session_activity) in a single transaction. The request record should still commit independently before the RPC to preserve the audit trail.

### Critical Pitfalls

1. **Transaction batching erases request audit trail** -- The current code commits the request record before calling Playwright, so failed RPCs still have a DB record. Naive batching loses this. Prevention: keep request commit separate; only batch post-RPC operations.

2. **MCP SDK version jump breaks protocol** -- The SDK is young and fast-moving. Prevention: pin ceiling version (`<2.0.0`), test full MCP handshake after upgrade.

3. **Debug code removal unmasks schema migration gap** -- The debug logging in operations.py acts as a canary for missing columns in old databases. Prevention: add startup schema validation or clear error message before removing debug code.

4. **JS injection fix assumes evaluate arg-passing** -- Playwright MCP may not support the `arg` parameter. Prevention: use `json.dumps(json.dumps(...))` + `JSON.parse()` pattern which works regardless.

5. **Combined evaluate changes error semantics** -- One failure kills entire state capture instead of partial capture. Prevention: try/catch each property access in the combined JS function.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Dependency Hygiene
**Rationale:** Independent of all code changes. Gets the build system correct. Catches breaking changes from version jumps before any code is modified.
**Delivers:** Correct pyproject.toml with all dependencies declared and version floors bumped; verified test suite passes with new versions.
**Addresses:** pydantic-settings missing dep, @playwright/mcp pin, version floor bumps, pydantic Config class migration to SettingsConfigDict.
**Avoids:** Pitfall #2 (MCP SDK breakage) by pinning ceiling; Pitfall #5 (Config deprecation) by migrating simultaneously; Pitfall #7 (npm cache mismatch) by checking current version before pinning; Pitfall #12 (pytest-asyncio) by running tests before code changes; Pitfall #13 (Ruff) by running check separately.

### Phase 2: Quick Bug Fixes
**Rationale:** All low-complexity, independent fixes. Each is 1-5 lines. Ship fast, reduce bug count before touching anything structural.
**Delivers:** Correct param serialization, accurate console error counts, working log level filtering, clean production logging.
**Addresses:** json.dumps fix, console_error_count fix, console log level filtering, debug logging removal.
**Avoids:** Pitfall #3 (schema migration gap) by pairing debug removal with startup validation; Pitfall #6 (console log format) by inspecting real stored data before writing parser; Pitfall #10 (mixed format) acknowledged as safe since field is write-only.

### Phase 3: Database Transaction Batching
**Rationale:** Foundational for Phase 4. Reduces fsync overhead. Must be done before evaluate consolidation because the snapshot flow benefits from both.
**Delivers:** `transaction()` async context manager on Database class; proxy endpoint uses single post-RPC transaction; snapshot cycle uses single transaction.
**Addresses:** Batch DB operations feature from FEATURES.md.
**Avoids:** Pitfall #1 (audit trail) by keeping request commit separate; Pitfall #9 (aiosqlite commit conflict) by adding `_in_transaction` flag.

### Phase 4: Evaluate Consolidation and Security Fix
**Rationale:** Groups related changes in session_state.py. The JS injection fix and evaluate batching use the same patterns (JSON data embedding, combined JS functions). Doing them together avoids touching the same file twice.
**Delivers:** 5x RPC reduction for state capture; N+M+K RPC reduction for state restore; JS injection surface closed.
**Addresses:** Combined capture_state, batched restore_state, JS injection fix.
**Avoids:** Pitfall #4 (evaluate arg-passing) by using JSON embedding; Pitfall #8 (partial failure) by adding try/catch per property.

### Phase Ordering Rationale

- Dependencies first because version changes can surface unexpected breakage that invalidates later work.
- Bug fixes before structural changes because they are independent, fast, and reduce cognitive load for later phases.
- Transactions before evaluate consolidation because the snapshot flow refactor in Phase 4 should use the transaction context manager from Phase 3.
- Security fix grouped with evaluate consolidation because they share the same file and same JSON-embedding pattern.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4:** Must verify Playwright MCP evaluate tool schema (does it accept `arg` parameter?) before implementation. Also need to test combined JS function on cross-origin pages.

Phases with standard patterns (skip research-phase):
- **Phase 1:** Straightforward dependency version bumps. Just run tests.
- **Phase 2:** One-line fixes with clear locations identified. No ambiguity.
- **Phase 3:** aiosqlite transaction pattern is well-documented. Architecture research provides the complete implementation pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Version data from uv.lock is authoritative. Missing dep confirmed by code inspection. |
| Features | HIGH | All bugs confirmed by line-level codebase analysis with specific line numbers. |
| Architecture | MEDIUM-HIGH | Patterns are sound and standard. Uncertainty only around Playwright MCP evaluate semantics. |
| Pitfalls | MEDIUM | Critical pitfalls well-identified from code analysis. MCP SDK evolution and Playwright MCP tool schema are low-confidence areas. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Playwright MCP evaluate arg support:** Must test at implementation time whether `browser_evaluate` accepts an `arg` parameter. The JSON-embedding fallback works either way, but knowing the answer determines the cleanest approach.
- **Console log blob format:** Must inspect real stored data from the database before writing the parser. Do not assume format from documentation.
- **@playwright/mcp current version:** Run `npm view @playwright/mcp version` and check npx cache before pinning. Could not verify during research.
- **MCP SDK 1.15+ changelog:** Could not verify breaking changes between 1.0 and 1.18. Test full handshake after upgrade.

## Sources

### Primary (HIGH confidence)
- `uv.lock` -- all resolved package versions (PyPI-resolved, authoritative)
- `pyproject.toml` -- current dependency specifications
- Direct codebase analysis of `operations.py`, `app.py`, `session_state.py`, `config.py`
- `.planning/codebase/CONCERNS.md` -- tech debt audit with line-level references

### Secondary (MEDIUM confidence)
- `.planning/PROJECT.md` -- project scope and constraints
- aiosqlite transaction semantics (training data, well-documented pattern)
- Pydantic v2 migration patterns (training data, well-documented)
- FastAPI lifespan patterns (training data, stable feature)

### Tertiary (LOW confidence)
- MCP SDK API stability across 1.0-1.18 (training data only, SDK is young)
- Playwright MCP `browser_evaluate` arg support (unverified, needs testing)
- @playwright/mcp npm version and changelog (web tools unavailable during research)

---
*Research completed: 2026-03-09*
*Ready for roadmap: yes*
