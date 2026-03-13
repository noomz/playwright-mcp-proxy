# Playwright MCP Proxy

## What This Is

A two-component Python system that wraps Playwright's MCP server with persistent SQLite storage, session management, diff-based content retrieval, and CLI management tooling. Used personally as a proxy between MCP clients (like Claude Desktop) and a Playwright browser subprocess.

## Core Value

Reliable browser automation proxy that persists all interactions and returns only metadata + diffs to minimize token usage for upstream LLM clients.

## Requirements

### Validated

- MCP stdio client exposing 9 tools to upstream clients -- existing
- HTTP server proxying requests to Playwright subprocess -- existing
- SQLite persistence of all requests/responses as raw blobs -- existing
- Diff-based content retrieval via SHA256 hash comparison -- existing
- Session state snapshots with periodic capture -- existing
- Subprocess health monitoring with auto-restart (3-strike, exponential backoff) -- existing
- Orphaned session detection on startup -- existing
- Search/grep-like content filtering on stored snapshots -- existing
- `pydantic-settings` added as explicit dependency, all version floors bumped -- v1.0
- `@playwright/mcp` pinned to specific version (0.0.68) -- v1.0
- Request params serialized via `json.dumps()` for valid JSON storage -- v1.0
- `console_error_count` reflects actual error count from stored logs -- v1.0
- Console log level filtering parses raw blob in fallback path -- v1.0
- Database operations batched into single transactions (3+ commits reduced to 2) -- v1.0
- Session state capture combines 5 sequential `browser_evaluate` RPCs into 1 -- v1.0
- `restore_state()` uses JSON embedding pattern to prevent JS injection -- v1.0
- `playwright-proxy-ctl` CLI with health, sessions, db vacuum commands -- v1.0
- Claude Code skill covering all 9 MCP tools with response policy and diff behavior -- v1.0
- Proxy-vs-direct comparison tests proving behavioral equivalence (5 scenarios) -- v1.0
- 3-way performance comparison (proxy vs direct vs Chrome) for 3 scenarios -- v1.0
- SKILL.md accuracy verified against actual codebase (phantom tools removed) -- v1.0

### Active

(None -- next milestone not yet planned)

### Backlog

- Implement list_sessions and resume_session MCP tools (wire existing HTTP endpoints to MCP layer)
- Comprehensive test coverage for MCP client, HTTP endpoints, PlaywrightManager
- Session cleanup/close flow with proper resource management
- Database migration strategy for safe schema upgrades

### Out of Scope

- Multi-session architecture / session pooling -- architectural change beyond current scope
- PostgreSQL migration -- SQLite sufficient for personal use
- Rate limiting / request throttling -- not needed for single-user local use
- Authentication on HTTP server -- localhost-only, single user
- Mobile/web UI -- CLI/MCP-only tool

## Context

- Personal project, sole user -- breaking API changes are acceptable
- Python 3.14 runtime, uv package manager, Hatchling build system
- v1.0 milestone completed 2026-03-13: modernization, tech debt cleanup, CLI tooling, skill docs, comparison testing
- 7,410 lines of Python across the codebase
- Timeline: 2025-10-22 (first commit) to 2026-03-13 (v1.0 shipped)

## Constraints

- **Runtime**: Python >= 3.12, Node.js for Playwright subprocess
- **Package manager**: uv (Astral)
- **Database**: SQLite via aiosqlite (no external DB server)
- **Backward compatibility**: Not required -- sole user

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Pin @playwright/mcp version | `@latest` risks silent breaking changes | Pinned to 0.0.68 (Phase 1) |
| Batch DB commits | Per-operation commits cause unnecessary overhead | 2-boundary commit model (Phase 3) |
| Single evaluate for state capture | 5 sequential RPCs is slow, 1 combined call is better | 80% RPC reduction with per-property try/catch (Phase 4) |
| Use JSON embedding pattern | f-string interpolation enables JS injection | json.dumps() for all user data in JS (Phase 4) |
| Click for CLI | Need hierarchical subcommands, sync interface | Click 8.x command groups for playwright-proxy-ctl (Phase 5) |
| DirectPlaywrightClient for tests | Need independent subprocess to compare against proxy | Standalone async JSON-RPC client with timeout guards (Phase 7) |
| Pre-recorded chrome measurements | Live chrome extension not available in CI | JSON fixture with manual measurements (Phase 8) |
| Remove phantom tools from SKILL.md | list_sessions/resume_session never existed in code | Cleaned in Phase 9 gap closure |

---
*Last updated: 2026-03-13 after v1.0 milestone completion*
