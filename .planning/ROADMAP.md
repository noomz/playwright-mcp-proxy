# Roadmap: Playwright MCP Proxy — Modernization & Tech Debt

## Overview

This milestone cleans up accumulated tech debt in a working MCP proxy system. It starts with dependency hygiene (get the build system correct), then fixes data-integrity bugs (quick wins that reduce bug count), then adds database transaction batching (structural performance improvement), and finishes by consolidating evaluate RPCs and closing a JS injection surface (related changes in the same file). Each phase delivers independently verifiable improvements.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Dependency Hygiene** - Correct all dependency declarations and version floors in pyproject.toml
- [ ] **Phase 2: Bug Fixes** - Fix data-integrity bugs in param serialization, console error counting, and log filtering
- [ ] **Phase 3: Transaction Batching** - Batch related DB writes into single transactions to reduce commit overhead
- [ ] **Phase 4: Evaluate Consolidation & Security** - Combine 5 evaluate RPCs into 1 and close JS injection surface in session state

## Phase Details

### Phase 1: Dependency Hygiene
**Goal**: All dependencies are correctly declared with appropriate version constraints, and the project builds and tests cleanly against resolved versions
**Depends on**: Nothing (first phase)
**Requirements**: DEPS-01, DEPS-02, DEPS-03
**Success Criteria** (what must be TRUE):
  1. `pydantic-settings` is an explicit dependency in pyproject.toml and `uv pip install -e .` succeeds in a clean environment
  2. All dependency version floors in pyproject.toml match or exceed the versions currently resolved in uv.lock
  3. `@playwright/mcp` is pinned to a specific version (not `@latest`) in the subprocess spawn command
  4. Existing test suite passes with no regressions after dependency updates
**Plans**: 1 plan

Plans:
- [ ] 01-01-PLAN.md — Update dependency declarations, pin @playwright/mcp@0.0.68, verify test suite

### Phase 2: Bug Fixes
**Goal**: All known data-integrity bugs are fixed so stored data is valid JSON, metadata reflects reality, and log filtering works correctly
**Depends on**: Phase 1
**Requirements**: BUGF-01, BUGF-02, BUGF-03
**Success Criteria** (what must be TRUE):
  1. Request params stored in the database are valid JSON (deserializable via `json.loads()`)
  2. `console_error_count` in proxy response metadata returns the actual count of error-level logs, not hardcoded 0
  3. Console log level filtering returns correct results even when only raw blob data exists (no normalized logs)
**Plans**: 1 plan

Plans:
- [ ] 02-01-PLAN.md — Fix param serialization, console error count, and log level filtering

### Phase 3: Transaction Batching
**Goal**: Related database writes are grouped into single transactions, reducing per-request commit overhead without losing the pre-RPC audit trail
**Depends on**: Phase 2
**Requirements**: PERF-01
**Success Criteria** (what must be TRUE):
  1. The proxy endpoint commits the request record before the Playwright RPC, then batches all post-RPC writes (response + session activity update) in a single transaction
  2. A failed Playwright RPC still has the request record persisted in the database (audit trail preserved)
  3. Total SQLite commits per proxy request are reduced from 3+ to 2 (one pre-RPC, one post-RPC)
**Plans**: TBD

Plans:
- [ ] 03-01: TBD

### Phase 4: Evaluate Consolidation & Security
**Goal**: Session state capture uses a single combined evaluate call instead of 5 sequential RPCs, and JS injection risk in state restoration is eliminated
**Depends on**: Phase 3
**Requirements**: PERF-02, SECR-01
**Success Criteria** (what must be TRUE):
  1. Session state capture issues 1 `browser_evaluate` RPC instead of 5, returning all state properties in a single call
  2. The combined JS function handles individual property failures gracefully (try/catch per property) so partial state is still captured
  3. `restore_state()` passes data via JSON embedding pattern (not f-string interpolation), eliminating the JS injection surface
**Plans**: TBD

Plans:
- [ ] 04-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Dependency Hygiene | 1/1 | Complete | 2026-03-10 |
| 2. Bug Fixes | 0/1 | Not started | - |
| 3. Transaction Batching | 0/0 | Not started | - |
| 4. Evaluate Consolidation & Security | 0/0 | Not started | - |
