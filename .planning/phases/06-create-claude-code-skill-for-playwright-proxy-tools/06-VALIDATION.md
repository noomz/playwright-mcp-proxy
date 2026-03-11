---
phase: 6
slug: create-claude-code-skill-for-playwright-proxy-tools
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/test_database.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** No automated test (documentation phase — produces SKILL.md)
- **After every plan wave:** Manual quality checklist review
- **Before `/gsd:verify-work`:** Skill file exists at correct path with complete content
- **Max feedback latency:** N/A (manual verification)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | Skill exists | manual | `test -f ~/.claude/skills/playwright-proxy/SKILL.md` | N/A | ⬜ pending |
| 06-01-02 | 01 | 1 | All 9 tools documented | manual | Cross-check vs mcp_server.py TOOLS | N/A | ⬜ pending |
| 06-01-03 | 01 | 1 | Quality criteria | manual | Apply skill-reviewer 10-point checklist | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements. This phase produces a documentation artifact (SKILL.md), not executable code.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Skill file has valid YAML frontmatter | Correct metadata | Frontmatter is declarative config | Open SKILL.md, verify `name`, `description`, `allowed-tools` present |
| All 9 tools documented | Complete coverage | Content review | Cross-check tool list against `mcp_server.py` TOOLS |
| Response policy explained | Critical contract | Prose clarity check | Verify SKILL.md explains ref_id → get_content flow |
| Diff behavior documented | Phase 2 contract | Prose clarity check | Verify empty-means-unchanged is explained |
| Passes skill-reviewer criteria | Quality gate | Subjective assessment | Run `/skill-reviewer` against SKILL.md |

---

## Validation Sign-Off

- [ ] All tasks have manual verification steps defined
- [ ] Sampling continuity: manual review after each task
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency acceptable for documentation phase
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
