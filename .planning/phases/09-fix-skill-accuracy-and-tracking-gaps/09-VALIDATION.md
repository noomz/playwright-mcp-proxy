---
phase: 9
slug: fix-skill-accuracy-and-tracking-gaps
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-13
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.0 |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/test_chrome_comparison.py -m chrome_comparison -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_chrome_comparison.py -m chrome_comparison -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | SKIL-02, SKIL-06 | manual-only | `grep -c "list_sessions\|resume_session" ~/.claude/skills/playwright-proxy/SKILL.md` = 0 | N/A | ⬜ pending |
| 09-01-02 | 01 | 1 | SKIL-01..06 | manual-only | `grep -E "\[x\] \*\*(SKIL)" .planning/REQUIREMENTS.md` = 6 lines | N/A | ⬜ pending |
| 09-01-03 | 01 | 1 | CHRM-01..03 | manual-only | `grep -E "\[x\] \*\*(CHRM)" .planning/REQUIREMENTS.md` = 3 lines | N/A | ⬜ pending |
| 09-01-04 | 01 | 1 | All 27 | manual-only | `grep "Pending" .planning/REQUIREMENTS.md` = 0 lines | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. No new test files needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SKILL.md lists exactly 9 tools | SKIL-02 | File lives outside project dir | `grep -c "^\| \\\`" ~/.claude/skills/playwright-proxy/SKILL.md` should return 9 |
| No phantom tools in SKILL.md | SKIL-06 | String search, not logic test | `grep -c "list_sessions\|resume_session" ~/.claude/skills/playwright-proxy/SKILL.md` should return 0 |
| All checkboxes checked | SKIL-01..06, CHRM-01..03 | Tracking file edit | `grep -E "\[ \] \*\*(SKIL|CHRM)" .planning/REQUIREMENTS.md` should return empty |
| Traceability all Complete | All 27 | Tracking file edit | `grep "Pending" .planning/REQUIREMENTS.md` should return empty |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
