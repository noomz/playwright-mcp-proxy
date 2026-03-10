---
phase: 2
slug: bug-fixes
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.0+ with pytest-asyncio 1.0.0+ |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]` — `asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/test_bugs.py -x` |
| **Full suite command** | `uv run pytest tests/ --cov=playwright_mcp_proxy` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_bugs.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | BUGF-01,02,03 | unit | `uv run pytest tests/test_bugs.py -x` | Wave 0 | pending |
| 02-01-02 | 01 | 1 | BUGF-01 | unit | `uv run pytest tests/test_bugs.py::test_request_params_valid_json -x` | Wave 0 | pending |
| 02-01-03 | 01 | 1 | BUGF-02 | unit | `uv run pytest tests/test_bugs.py::test_console_error_count_nonzero -x` | Wave 0 | pending |
| 02-01-04 | 01 | 1 | BUGF-03 | unit | `uv run pytest tests/test_bugs.py::test_console_blob_filter_error_only -x` | Wave 0 | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_bugs.py` — stubs for BUGF-01, BUGF-02, BUGF-03
- [ ] No framework install needed — pytest and pytest-asyncio already in `[dev]` dependencies

*Existing infrastructure covers framework requirements.*

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
