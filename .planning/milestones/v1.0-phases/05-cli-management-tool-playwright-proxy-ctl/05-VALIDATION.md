---
phase: 5
slug: cli-management-tool-playwright-proxy-ctl
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/test_ctl.py -v` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_ctl.py -v`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 3 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | CLI-HEALTH | unit | `uv run pytest tests/test_ctl.py -k health` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | CLI-SESSIONS | unit | `uv run pytest tests/test_ctl.py -k sessions` | ❌ W0 | ⬜ pending |
| 05-01-03 | 01 | 1 | CLI-DB | unit | `uv run pytest tests/test_ctl.py -k db` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_ctl.py` — stubs for CLI commands using Click CliRunner
- [ ] `click>=8.0` added to pyproject.toml dependencies

*Test file created in Wave 0 of plan execution.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| db vacuum on live DB | CLI-DB | Requires real SQLite file | Run `playwright-proxy-ctl db vacuum` on proxy.db |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 3s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
