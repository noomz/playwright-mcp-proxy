---
phase: 3
slug: transaction-batching
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3+ with pytest-asyncio 1.0+ |
| **Config file** | `pyproject.toml` — `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` |
| **Quick run command** | `uv run pytest tests/test_transaction_batching.py -x` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~3 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_transaction_batching.py -x`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 0 | PERF-01 | unit | `uv run pytest tests/test_transaction_batching.py -x` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | PERF-01 | unit | `uv run pytest tests/test_transaction_batching.py::test_no_commit_methods_do_not_commit -x` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 1 | PERF-01 | unit | `uv run pytest tests/test_transaction_batching.py::test_post_rpc_writes_batch_committed -x` | ❌ W0 | ⬜ pending |
| 3-01-04 | 01 | 2 | PERF-01 | unit | `uv run pytest tests/test_transaction_batching.py::test_request_committed_before_rpc -x` | ❌ W0 | ⬜ pending |
| 3-01-05 | 01 | 2 | PERF-01 | unit | `uv run pytest tests/test_transaction_batching.py::test_error_path_batch_committed -x` | ❌ W0 | ⬜ pending |
| 3-01-06 | 01 | 2 | PERF-01 | regression | `uv run pytest` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_transaction_batching.py` — stubs for PERF-01 (request durability, batch commit, error path, no-commit methods)

*Existing infrastructure (`tests/test_database.py`, `tests/test_diff.py`, `tests/test_bugs.py`) covers prior phases and serves as regression baseline.*

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
