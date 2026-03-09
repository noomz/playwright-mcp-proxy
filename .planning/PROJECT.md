# Playwright MCP Proxy — Modernization & Tech Debt

## What This Is

A two-component Python system that wraps Playwright's MCP server with persistent SQLite storage, session management, and diff-based content retrieval. Used personally as a proxy between MCP clients (like Claude Desktop) and a Playwright browser subprocess.

## Core Value

Reliable browser automation proxy that persists all interactions and returns only metadata + diffs to minimize token usage for upstream LLM clients.

## Requirements

### Validated

- MCP stdio client exposing 9 tools to upstream clients — existing
- HTTP server proxying requests to Playwright subprocess — existing
- SQLite persistence of all requests/responses as raw blobs — existing
- Diff-based content retrieval via SHA256 hash comparison — existing
- Session state snapshots with periodic capture — existing
- Subprocess health monitoring with auto-restart (3-strike, exponential backoff) — existing
- Orphaned session detection on startup — existing
- Search/grep-like content filtering on stored snapshots — existing

### Active

- [ ] Update all Python dependencies to latest compatible versions
- [ ] Add missing `pydantic-settings` dependency to pyproject.toml
- [ ] Pin `@playwright/mcp` to specific version (not `@latest`)
- [ ] Fix hardcoded `console_error_count = 0` — actually count errors from stored logs
- [ ] Fix console log level filtering — parse blob in fallback path
- [ ] Remove debug logging left in `operations.py` (field-by-field iteration loops)
- [ ] Fix `str(params)` → `json.dumps(params)` for proper serialization
- [ ] Fix JS injection risk in `session_state.py` — use arg passing instead of f-string interpolation
- [ ] Batch related DB operations into transactions (reduce per-operation commits)
- [ ] Combine 5 sequential `browser_evaluate` RPCs into single call for state capture

### Out of Scope

- Adding comprehensive test coverage — separate future milestone
- Multi-session architecture / session pooling — architectural change beyond current scope
- Database migration framework — not needed until schema changes again
- Rate limiting / request throttling — not needed for single-user local use
- Authentication on HTTP server — localhost-only, single user
- PostgreSQL migration — SQLite sufficient for personal use

## Context

- Personal project, sole user — breaking API changes are acceptable
- Brownfield codebase with working Phase 1 (core proxy), Phase 2 (diff), Phase 7 (session state) features
- Python 3.14 runtime, uv package manager, Hatchling build system
- Dependencies have minimum versions pinned but may be outdated
- CONCERNS.md documents 6 tech debt items, 3 security issues, 3 performance bottlenecks
- Existing codebase map at `.planning/codebase/`

## Constraints

- **Runtime**: Python >= 3.12, Node.js for Playwright subprocess
- **Package manager**: uv (Astral)
- **Database**: SQLite via aiosqlite (no external DB server)
- **Backward compatibility**: Not required — sole user

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pin @playwright/mcp version | `@latest` risks silent breaking changes | — Pending |
| Batch DB commits | Per-operation commits cause unnecessary overhead | — Pending |
| Single evaluate for state capture | 5 sequential RPCs is slow, 1 combined call is better | — Pending |
| Use evaluate arg passing | f-string interpolation enables JS injection | — Pending |

---
*Last updated: 2026-03-09 after initialization*
