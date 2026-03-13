---
phase: 4
slug: evaluate-consolidation-security
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` (asyncio_mode=auto) |
| **Quick run command** | `uv run pytest tests/test_phase7_state_capture.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_phase7_state_capture.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 0 | PERF-02 | unit | `uv run pytest tests/test_phase7_state_capture.py::test_capture_state_partial_failure -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 0 | SECR-01 | unit | `uv run pytest tests/test_phase7_state_capture.py::test_restore_state_injection_safety -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 0 | SECR-01 | unit | `uv run pytest tests/test_phase7_state_capture.py::test_restore_state_special_chars -x` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | PERF-02 | unit | `uv run pytest tests/test_phase7_state_capture.py::test_capture_state -x` | ✅ (update) | ⬜ pending |
| 04-01-05 | 01 | 1 | SECR-01 | unit | `uv run pytest tests/test_phase7_state_capture.py::test_restore_state -x` | ✅ (update) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_phase7_state_capture.py::test_capture_state_partial_failure` — stub for PERF-02 graceful partial state
- [ ] `tests/test_phase7_state_capture.py::test_restore_state_injection_safety` — stub for SECR-01 (no f-string injection)
- [ ] `tests/test_phase7_state_capture.py::test_restore_state_special_chars` — stub for SECR-01 (special chars in keys/values)
- [ ] Update `test_capture_state` and `test_capture_state_empty_cookies`: change `call_count == 5` to `call_count == 1`, update mock

*Existing infrastructure covers framework needs. Only new test stubs required.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
