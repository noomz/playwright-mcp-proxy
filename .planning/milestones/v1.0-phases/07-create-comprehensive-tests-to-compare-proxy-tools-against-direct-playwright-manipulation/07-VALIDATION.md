---
phase: 7
slug: create-comprehensive-tests-to-compare-proxy-tools-against-direct-playwright-manipulation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-11
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.3.0+ with pytest-asyncio 1.0.0+ |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/test_comparison.py -v -m integration -x` |
| **Full suite command** | `uv run pytest -v` |
| **Estimated runtime** | ~30 seconds (requires running server + network) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/ -v --ignore=tests/test_comparison.py --ignore=tests/test_integration_live.py` (unit tests only)
- **After every plan wave:** `uv run pytest tests/ -v -m "not integration"`
- **Before `/gsd:verify-work`:** `uv run pytest tests/test_comparison.py -v` (full integration, requires server)
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | Scenario 1: simple navigation | integration | `uv run pytest tests/test_comparison.py::test_scenario1_simple_navigation -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | Scenario 2: diff behavior | integration | `uv run pytest tests/test_comparison.py::test_scenario2_diff_behavior -x` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | Scenario 3: multi-page navigation | integration | `uv run pytest tests/test_comparison.py::test_scenario3_multi_page_navigation -x` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 1 | Scenario 4: content search | integration | `uv run pytest tests/test_comparison.py::test_scenario4_content_search -x` | ❌ W0 | ⬜ pending |
| 07-01-05 | 01 | 1 | Scenario 5: error handling | integration | `uv run pytest tests/test_comparison.py::test_scenario5_error_handling -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_comparison.py` — new file with DirectPlaywrightClient helper and 5 scenarios
- [ ] `@pytest.mark.integration` marker — consistent with `test_integration_live.py`

*All test infrastructure (pytest, pytest-asyncio, httpx) already exists.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Tests require running server | Integration prerequisite | Server must be started separately | Start `playwright-proxy-server`, then run `uv run pytest tests/test_comparison.py -v` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
