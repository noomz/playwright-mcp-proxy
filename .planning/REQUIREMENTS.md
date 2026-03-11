# Requirements: Playwright MCP Proxy — Modernization & Tech Debt

**Defined:** 2026-03-09
**Core Value:** Reliable browser automation proxy that persists all interactions and returns only metadata + diffs to minimize token usage

## v1 Requirements

Requirements for this milestone. Each maps to roadmap phases.

### Dependencies

- [x] **DEPS-01**: `pydantic-settings` added as explicit dependency in pyproject.toml
- [x] **DEPS-02**: All dependency version floors bumped to match tested/locked versions
- [x] **DEPS-03**: `@playwright/mcp` pinned to specific version instead of `@latest`

### Bug Fixes

- [x] **BUGF-01**: Request params serialized via `json.dumps()` instead of `str()` for valid JSON storage
- [x] **BUGF-02**: `console_error_count` in proxy response metadata reflects actual error count from stored logs
- [x] **BUGF-03**: Console log level filtering parses raw blob in fallback path when no normalized logs exist

### Performance

- [x] **PERF-01**: Related database operations batched into single transactions (reduce 3+ commits per request to 1)
- [x] **PERF-02**: Session state capture combines 5 sequential `browser_evaluate` RPCs into single call

### Security

- [x] **SECR-01**: `restore_state()` uses JSON embedding pattern instead of f-string interpolation to prevent JS injection

### CLI Management Tool

- [x] **CLI-01**: `playwright-proxy-ctl health` checks server health via HTTP and prints status or connection error
- [x] **CLI-02**: `playwright-proxy-ctl sessions list` lists sessions from server HTTP API with optional `--state` filter
- [x] **CLI-03**: `playwright-proxy-ctl sessions clear` deletes sessions by state from DB directly with confirmation prompt
- [x] **CLI-04**: `playwright-proxy-ctl db vacuum` compacts SQLite database (requires server stopped)

### Claude Code Skill

- [ ] **SKIL-01**: Skill file exists at `~/.claude/skills/playwright-proxy/SKILL.md` with valid YAML frontmatter (name, description, allowed-tools)
- [ ] **SKIL-02**: All 9 MCP tools documented with parameters and return values
- [ ] **SKIL-03**: Response policy (metadata + ref_id, then get_content) explained as standard workflow
- [ ] **SKIL-04**: Diff behavior documented (empty = unchanged, reset_cursor for full content)
- [ ] **SKIL-05**: playwright-proxy-ctl commands (health, sessions list/clear, db vacuum) documented
- [ ] **SKIL-06**: Skill follows progressive disclosure and passes skill-reviewer quality criteria

### Comparison Tests

- [x] **CMP-01**: Proxy and direct Playwright return same landmark content for simple page navigation (example.com)
- [x] **CMP-02**: Proxy diff suppresses unchanged content on second read while direct always returns full content
- [x] **CMP-03**: Both paths correctly reflect page content across multi-page navigation (example.com then httpbin.org)
- [x] **CMP-04**: Proxy search_for parameter filters snapshot content to fewer lines than full response
- [x] **CMP-05**: Both paths handle invalid URL navigation gracefully without crashes

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
| DEPS-01 | Phase 1 | Complete |
| DEPS-02 | Phase 1 | Complete |
| DEPS-03 | Phase 1 | Complete |
| BUGF-01 | Phase 2 | Complete |
| BUGF-02 | Phase 2 | Complete |
| BUGF-03 | Phase 2 | Complete |
| PERF-01 | Phase 3 | Complete |
| PERF-02 | Phase 4 | Complete |
| SECR-01 | Phase 4 | Complete |
| CLI-01 | Phase 5 | Complete |
| CLI-02 | Phase 5 | Complete |
| CLI-03 | Phase 5 | Complete |
| CLI-04 | Phase 5 | Complete |
| SKIL-01 | Phase 6 | Planned |
| SKIL-02 | Phase 6 | Planned |
| SKIL-03 | Phase 6 | Planned |
| SKIL-04 | Phase 6 | Planned |
| SKIL-05 | Phase 6 | Planned |
| SKIL-06 | Phase 6 | Planned |
| CMP-01 | Phase 7 | Planned |
| CMP-02 | Phase 7 | Planned |
| CMP-03 | Phase 7 | Planned |
| CMP-04 | Phase 7 | Planned |
| CMP-05 | Phase 7 | Planned |

**Coverage:**
- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0

---
*Requirements defined: 2026-03-09*
*Last updated: 2026-03-11 after Phase 7 planning*
