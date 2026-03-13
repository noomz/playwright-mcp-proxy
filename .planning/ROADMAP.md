# Roadmap: Playwright MCP Proxy

## Completed Milestones

<details>
<summary><strong>v1.0 Modernization & Tech Debt</strong> (9 phases, 27 requirements, shipped 2026-03-13)</summary>

Dependency hygiene, data-integrity bug fixes, transaction batching, JS injection closure, CLI tooling (playwright-proxy-ctl), Claude Code skill documentation, proxy-vs-direct comparison tests, and 3-way Chrome performance comparison.

| Phase | Description | Completed |
|-------|-------------|-----------|
| 1. Dependency Hygiene | Pin deps, add pydantic-settings, pin @playwright/mcp@0.0.68 | 2026-03-10 |
| 2. Bug Fixes | Fix params serialization, console error count, log filtering | 2026-03-10 |
| 3. Transaction Batching | Reduce SQLite commits per request from 3+ to 2 | 2026-03-10 |
| 4. Evaluate Consolidation & Security | Combine 5 RPCs to 1, close JS injection surface | 2026-03-10 |
| 5. CLI Management Tool | playwright-proxy-ctl with health, sessions, db vacuum | 2026-03-11 |
| 6. Claude Code Skill | SKILL.md covering all 9 tools, response policy, diff behavior | 2026-03-11 |
| 7. Comparison Tests | 5 proxy-vs-direct scenarios proving behavioral equivalence | 2026-03-11 |
| 8. Chrome Comparison | 3-way perf table (proxy vs direct vs Chrome) for 3 scenarios | 2026-03-12 |
| 9. SKILL.md Accuracy | Remove phantom tools, close all tracking gaps | 2026-03-13 |

See `.planning/milestones/` for archived ROADMAP, REQUIREMENTS, and audit.

</details>

## Next Milestone

Not yet planned. Candidate work from backlog:
- Implement list_sessions and resume_session MCP tools
- Comprehensive test coverage
- Session cleanup/close flow
- Database migration strategy
