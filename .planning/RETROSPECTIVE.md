# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 -- Modernization & Tech Debt

**Shipped:** 2026-03-13
**Phases:** 9 | **Plans:** 9 | **Timeline:** 2026-03-09 to 2026-03-13 (5 days)

### What Was Built
- Fixed dependency declarations and pinned @playwright/mcp@0.0.68 for reproducible builds
- Fixed 3 data-integrity bugs: params serialization, console error counting, log level filtering
- Transaction batching reduces SQLite commits per request from 3+ to 2
- Combined 5 sequential browser_evaluate RPCs into 1 (80% reduction) with per-property error handling
- Closed JS injection surface in session state restoration via json.dumps embedding
- playwright-proxy-ctl CLI with health check, session management, and database vacuum
- Claude Code SKILL.md covering all 9 MCP tools, response policy, diff behavior, and ctl commands
- Proxy-vs-direct comparison test suite (5 scenarios) proving behavioral equivalence
- 3-way performance comparison table (proxy vs direct Playwright vs Chrome extension)
- Gap closure pass removing phantom tools and fixing all requirement tracking

### What Worked
- Phased approach with independent verification at each step kept momentum high
- Starting with dependency hygiene gave a clean foundation for all subsequent phases
- Grouping related changes (evaluate consolidation + security) reduced context switching
- Pre-recorded chrome measurements avoided flaky CI dependency on browser extension
- Gap closure phase (Phase 9) caught documentation drift before shipping

### What Was Inefficient
- STATE.md progress tracking fell behind (showed 62% and Phase 3 focus when all 9 phases were complete)
- Summary extraction tooling returned empty for all phases (frontmatter format mismatch)
- Phase 6 (SKILL.md) documented tools that did not exist, requiring Phase 9 cleanup pass

### Patterns Established
- Two-boundary commit model for proxy requests (pre-RPC audit + post-RPC batch)
- DirectPlaywrightClient pattern for independent subprocess comparison testing
- JSON fixture approach for external tool measurements (chrome extension data)
- Gap closure phase as final milestone step to catch documentation drift

### Key Lessons
1. Document only what exists in code -- aspirational tool documentation creates confusion and requires cleanup
2. Milestone audit before shipping catches tracking gaps that accumulate across phases
3. Per-property try/catch in combined JS evaluation is essential -- partial state capture beats total failure
4. Click command groups scale well for CLI with mixed sync/async operations (asyncio.run bridge)

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Phases | Plans | Key Change |
|-----------|--------|-------|------------|
| v1.0 | 9 | 9 | Established phased modernization with gap closure |

### Top Lessons (Verified Across Milestones)

1. Document what exists, not what is planned -- keep skill docs in sync with code
2. Milestone audit + gap closure phase prevents shipping with tracking drift
