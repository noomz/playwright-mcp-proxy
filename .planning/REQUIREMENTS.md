# Requirements: Playwright MCP Proxy — Modernization & Tech Debt

**Defined:** 2026-03-09
**Core Value:** Reliable browser automation proxy that persists all interactions and returns only metadata + diffs to minimize token usage

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Dependencies

- [ ] **DEPS-01**: `pydantic-settings` added as explicit dependency in pyproject.toml
- [ ] **DEPS-02**: All dependency version floors bumped to match tested/locked versions
- [ ] **DEPS-03**: `@playwright/mcp` pinned to specific version instead of `@latest`

### Bug Fixes

- [ ] **BUGF-01**: Request params serialized via `json.dumps()` instead of `str()` for valid JSON storage
- [ ] **BUGF-02**: `console_error_count` in proxy response metadata reflects actual error count from stored logs
- [ ] **BUGF-03**: Console log level filtering parses raw blob in fallback path when no normalized logs exist

### Performance

- [ ] **PERF-01**: Related database operations batched into single transactions (reduce 3+ commits per request to 1)
- [ ] **PERF-02**: Session state capture combines 5 sequential `browser_evaluate` RPCs into single call

### Security

- [ ] **SECR-01**: `restore_state()` uses JSON embedding pattern instead of f-string interpolation to prevent JS injection

## v2 Requirements

Deferred to future milestone.

### Code Quality

- **QUAL-01**: Debug logging removed from `operations.py` (field-by-field iteration loops) with startup schema validation as replacement
- **QUAL-02**: Comprehensive test coverage for MCP client, HTTP endpoints, PlaywrightManager

### Features

- **FEAT-01**: Session cleanup/close flow with proper resource management
- **FEAT-02**: Database migration strategy for safe schema upgrades

## Out of Scope

| Feature | Reason |
|---------|--------|
| Multi-session architecture | Architectural change beyond modernization scope |
| PostgreSQL migration | SQLite sufficient for personal use |
| Rate limiting | Not needed for single-user local use |
| HTTP authentication | Localhost-only, single user |
| Mobile/web UI | CLI/MCP-only tool |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEPS-01 | Phase 1 | Pending |
| DEPS-02 | Phase 1 | Pending |
| DEPS-03 | Phase 1 | Pending |
| BUGF-01 | Phase 2 | Pending |
| BUGF-02 | Phase 2 | Pending |
| BUGF-03 | Phase 2 | Pending |
| PERF-01 | Phase 3 | Pending |
| PERF-02 | Phase 4 | Pending |
| SECR-01 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 9 total
- Mapped to phases: 9
- Unmapped: 0

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-09 after roadmap creation*
