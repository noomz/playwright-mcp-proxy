---
phase: 8
slug: add-new-perf-comparison-results-between-claude-in-chrome
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-12
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_chrome_comparison.py -v` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~10 seconds (JSON fixture load, no browser) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_chrome_comparison.py -v`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | TBD | integration | `uv run pytest tests/test_chrome_comparison.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_chrome_comparison.py` — chrome comparison test with JSON fixture loading
- [ ] `tests/chrome_measurements.json` — measurement data recorded during interactive chrome sessions

*Existing test infrastructure (conftest, pytest config) covers framework needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Chrome measurement recording | TBD | Requires Claude in Chrome extension in active browser session | Run chrome scenarios interactively, verify JSON output |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
