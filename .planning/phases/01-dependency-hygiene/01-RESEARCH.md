# Phase 1: Dependency Hygiene - Research

**Researched:** 2026-03-10
**Domain:** Python packaging (pyproject.toml, uv.lock), npm subprocess pinning
**Confidence:** HIGH

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DEPS-01 | `pydantic-settings` added as explicit dependency in pyproject.toml | Confirmed missing from pyproject.toml; resolved version 2.11.0 found in uv.lock as transitive dep of `mcp` |
| DEPS-02 | All dependency version floors bumped to match tested/locked versions | All resolved versions extracted from uv.lock; floor deltas documented per package below |
| DEPS-03 | `@playwright/mcp` pinned to specific version instead of `@latest` | `@latest` located in `config.py` (playwright_args field default) and `.mcp.json`; current npm version is 0.0.68 |
</phase_requirements>

---

## Summary

Phase 1 is a pure packaging and configuration fix with zero runtime logic changes. The codebase has three dependency hygiene problems that are straightforward to fix but create real fragility if left in place.

First, `pydantic-settings` is imported directly in `config.py` via `from pydantic_settings import BaseSettings` but is absent from `pyproject.toml`. It resolves today only because `mcp>=1.0.0` happens to pull it transitively. If the `mcp` SDK ever drops that dep (or if someone installs `playwright-mcp-proxy` without `mcp` already in the environment), the import fails with no clear error message. The fix is a one-line addition to `pyproject.toml`.

Second, 7 of 8 declared runtime dependencies have version floors significantly below the versions actually resolved in `uv.lock`. This means a fresh install could pull in older, untested versions that may behave differently. The fix is bumping each floor to the resolved version (or near it) with appropriate conservatism.

Third, `@playwright/mcp@latest` is used as the subprocess argument in two places: the `playwright_args` default in `config.py` and the `args` list in `.mcp.json`. This means every `npx` invocation can silently pull a different version, making the system non-reproducible. The current npm-published version is `0.0.68`. Both locations must be updated.

**Primary recommendation:** Edit `pyproject.toml` to add `pydantic-settings>=2.11.0` and bump all floors to match locked versions; update `config.py` default and `.mcp.json` to pin `@playwright/mcp@0.0.68`; run `uv lock` then `uv run pytest` to verify.

---

## Standard Stack

### Resolved Versions (from uv.lock — authoritative)

| Package | Declared Floor | Resolved Version | Gap | Action |
|---------|---------------|-----------------|-----|--------|
| fastapi | >=0.115.0 | 0.119.1 | 4 minor | Bump to >=0.119.0 |
| uvicorn | >=0.32.0 | 0.38.0 | 6 minor | Bump to >=0.34.0 |
| aiosqlite | >=0.20.0 | 0.21.0 | 1 minor | Bump to >=0.21.0 |
| mcp | >=1.0.0 | 1.18.0 | 18 minor | Bump to >=1.15.0 |
| httpx | >=0.27.0 | 0.28.1 | 1 minor | Bump to >=0.28.0 |
| pydantic | >=2.9.0 | 2.12.3 | 3 minor | Bump to >=2.10.0 |
| python-dotenv | >=1.0.0 | 1.1.1 | 1 minor | Keep >=1.0.0 (stable) |
| psutil | >=6.1.0 | 7.1.1 | 1 major | Keep >=6.1.0 (API stable for this usage) |
| **pydantic-settings** | **MISSING** | **2.11.0** | — | **ADD >=2.11.0** |

### Dev Dependencies

| Package | Declared Floor | Resolved Version | Gap | Action |
|---------|---------------|-----------------|-----|--------|
| pytest | >=8.3.0 | 8.4.2 | 1 minor | Keep >=8.3.0 |
| pytest-asyncio | >=0.24.0 | 1.2.0 | MAJOR (0.x -> 1.x) | Bump to >=1.0.0 |
| pytest-cov | >=6.0.0 | 7.0.0 | 1 major | Bump to >=6.0.0 (keep, API stable) |
| ruff | >=0.7.0 | 0.14.1 | significant | Bump to >=0.9.0 |

### External npm Package

| Package | Current Spec | Resolved (actual) | Action |
|---------|-------------|------------------|--------|
| @playwright/mcp | @latest (unpinned) | 0.0.68 (current npm) | Pin to @0.0.68 |

---

## Architecture Patterns

### Where `@playwright/mcp@latest` Lives

Two locations, both must be updated:

1. **`playwright_mcp_proxy/config.py` line 29** — `playwright_args` field default value:
   ```python
   playwright_args: list[str] = Field(
       default=["@playwright/mcp@latest"],   # change to ["@playwright/mcp@0.0.68"]
       description="Arguments for Playwright MCP",
   )
   ```

2. **`.mcp.json` line 6** — the `args` array for the Claude Desktop MCP server config:
   ```json
   {
     "mcpServers": {
       "playwright": {
         "command": "npx",
         "args": ["@playwright/mcp@latest"]   // change to ["@playwright/mcp@0.0.68"]
       }
     }
   }
   ```

### Where `pydantic-settings` Is Used

One import location: `playwright_mcp_proxy/config.py` line 7:
```python
from pydantic_settings import BaseSettings
```

The `Settings` class inherits from `BaseSettings` and uses it for env prefix resolution and `.env` file loading. This is a direct, first-class usage — not an internal import re-exported by another library.

### Config Class Migration Note

The `Settings` class currently uses the older `class Config` inner class pattern:
```python
class Config:
    env_prefix = "PLAYWRIGHT_PROXY_"
    env_file = ".env"
    env_file_encoding = "utf-8"
```

With `pydantic-settings>=2.0`, the preferred pattern is `model_config = SettingsConfigDict(...)`. The inner `class Config` is still supported but generates a deprecation warning in newer versions. This phase can migrate it as part of declaring `pydantic-settings` explicitly, or leave it for a later cleanup pass — both are acceptable since it is not broken.

### Recommended `pyproject.toml` After Changes

```toml
[project]
dependencies = [
    "fastapi>=0.119.0",
    "uvicorn>=0.34.0",
    "aiosqlite>=0.21.0",
    "mcp>=1.15.0",
    "httpx>=0.28.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.11.0",
    "python-dotenv>=1.0.0",
    "psutil>=6.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=1.0.0",
    "pytest-cov>=6.0.0",
    "ruff>=0.9.0",
]
```

### Update Sequence

```bash
# 1. Edit pyproject.toml (add pydantic-settings, bump floors)
# 2. Edit playwright_mcp_proxy/config.py (pin playwright_args default)
# 3. Edit .mcp.json (pin args)
# 4. Regenerate lockfile
uv lock

# 5. Install with dev extras
uv pip install -e ".[dev]"

# 6. Verify linting still passes (ruff may flag new issues at 0.14.x)
uv run ruff check .

# 7. Verify full test suite
uv run pytest -v
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Version range validation | Custom semver parser | uv's resolver | uv enforces constraints at install time; manual validation is redundant |
| npm version detection | Shell script | `npm view @playwright/mcp version` | One command, authoritative |
| Lockfile regeneration | Manual hash updates | `uv lock` | uv handles the full resolution graph |

---

## Common Pitfalls

### Pitfall 1: Pinning `@playwright/mcp` Without Checking Cache
**What goes wrong:** Developer pins to 0.0.68 but `npx` uses a locally cached older version because the cache was populated before pinning.
**Why it happens:** `npx` caches packages globally; pinning the spec string does not flush existing cache entries.
**How to avoid:** After pinning, run `npx --yes @playwright/mcp@0.0.68 --version` explicitly to confirm the correct version is fetched.
**Warning signs:** Server logs show a different tool set than expected from 0.0.68.

### Pitfall 2: `uv lock` Fails Due to Conflicting Constraints
**What goes wrong:** Bumping `mcp>=1.15.0` conflicts with another package that requires `mcp<1.15`.
**Why it happens:** Transitive dependency upper-bound constraints can conflict with bumped floors.
**How to avoid:** Run `uv lock` immediately after each floor bump and check resolver output. If conflict arises, check which transitive dep is the culprit using `uv tree`.
**Warning signs:** `uv lock` exits with `ResolutionImpossible` error.

### Pitfall 3: pytest-asyncio 1.x Changes Fixture Behavior
**What goes wrong:** Async fixtures that worked in 0.x behave differently in 1.x — specifically, fixture scope handling changed.
**Why it happens:** pytest-asyncio 1.0 overhauled fixture loop lifecycle management.
**How to avoid:** Run the full test suite (`uv run pytest -v`) and examine any failures carefully. The project already uses `asyncio_mode = "auto"` which is now the default, so basic async tests should pass. Watch for `ScopeMismatch` or `FixtureError` on fixtures that mix scopes.
**Warning signs:** Tests that previously passed silently fail with asyncio-related fixture errors.

### Pitfall 4: Ruff 0.14 Flags New Issues
**What goes wrong:** After bumping `ruff>=0.9.0`, the resolved version (0.14.1) reports new lint violations under existing rule categories (E, F, I, N, W).
**Why it happens:** Ruff adds rules to existing categories across versions. Even conservative rule sets accumulate new checks.
**How to avoid:** Run `uv run ruff check .` after install and fix any new violations before running tests. Do not add the violations to the ignore list without understanding them.
**Warning signs:** `ruff check .` exits non-zero after the upgrade.

### Pitfall 5: `.mcp.json` Is Missed
**What goes wrong:** `config.py` is updated but `.mcp.json` still uses `@latest`, leaving Claude Desktop's direct spawn unpinned.
**Why it happens:** Two separate locations reference the package spec string; it is easy to update only one.
**How to avoid:** Search for `@playwright/mcp` across the entire repository before considering the task complete: `rg '@playwright/mcp' .`
**Warning signs:** Post-change grep still returns `@latest` in any file.

---

## Code Examples

### Adding pydantic-settings to pyproject.toml
```toml
# Source: pyproject.toml [project] section
dependencies = [
    "fastapi>=0.119.0",
    "uvicorn>=0.34.0",
    "aiosqlite>=0.21.0",
    "mcp>=1.15.0",
    "httpx>=0.28.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.11.0",   # NEW: was missing
    "python-dotenv>=1.0.0",
    "psutil>=6.1.0",
]
```

### Pinning playwright_args in config.py
```python
# Source: playwright_mcp_proxy/config.py
playwright_args: list[str] = Field(
    default=["@playwright/mcp@0.0.68"],   # was: @playwright/mcp@latest
    description="Arguments for Playwright MCP",
)
```

### Pinning .mcp.json
```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": [
        "@playwright/mcp@0.0.68"
      ]
    }
  }
}
```

### Optional: Migrate Config class to SettingsConfigDict (pydantic-settings 2.x preferred style)
```python
# Source: pydantic-settings 2.x official docs
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PLAYWRIGHT_PROXY_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
    # ... fields unchanged
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `class Config` inner class in pydantic-settings | `model_config = SettingsConfigDict(...)` | pydantic-settings 2.0 (2023) | Inner class still works but generates DeprecationWarning in newer versions |
| `pytest-asyncio` per-test `@pytest.mark.asyncio` decorator | `asyncio_mode = "auto"` in pytest config | pytest-asyncio 0.21 | Project already uses auto mode; 1.x makes it the default |

**Deprecated/outdated:**
- `class Config` in pydantic-settings: Not broken but deprecated. Replacement is `model_config = SettingsConfigDict(...)`.
- `@playwright/mcp@latest` as subprocess arg: Functionally works but is non-reproducible and a stability risk.

---

## Open Questions

1. **Does pinning `@playwright/mcp@0.0.68` break anything in the running environment?**
   - What we know: The npm-published latest is 0.0.68 as of 2026-03-10. The project currently uses `@latest` which resolves to this same version.
   - What's unclear: Whether there is a locally cached version that differs.
   - Recommendation: Run `npx @playwright/mcp@0.0.68 --version` before and after the change to confirm the binary version matches expectations.

2. **Should the `class Config` inner class be migrated to `SettingsConfigDict` in this phase?**
   - What we know: It still works. It generates a deprecation warning in pydantic-settings 2.x.
   - What's unclear: Whether the project is seeing warnings currently (depends on pydantic-settings version).
   - Recommendation: Migrate it in this phase since the file is already being touched for the `playwright_args` pin. It is a 5-line mechanical change with no risk.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/test_database.py tests/test_diff.py -x` |
| Full suite command | `uv run pytest -v` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEPS-01 | `pydantic-settings` importable as explicit dep (not transitive only) | smoke | `uv run python -c "from pydantic_settings import BaseSettings; print('ok')"` | ✅ (import in config.py, not a test file) |
| DEPS-02 | Existing tests pass with bumped version floors | regression | `uv run pytest -v` | ✅ tests/ directory with 5 test files |
| DEPS-03 | `@playwright/mcp` pinned version used in subprocess spawn | manual | Inspect subprocess args in server startup logs | N/A — subprocess, not unit-testable |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_database.py tests/test_diff.py -x`
- **Per wave merge:** `uv run pytest -v`
- **Phase gate:** Full suite green (`uv run pytest -v`) before moving to Phase 2

### Wave 0 Gaps
- None — existing test infrastructure (5 test files, 14+ tests) covers the regression surface for DEPS-02. DEPS-01 is verified by the install itself succeeding without `mcp` providing the transitive dep. DEPS-03 requires manual inspection of subprocess command.

---

## Sources

### Primary (HIGH confidence)
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/uv.lock` — all resolved package versions (PyPI-authoritative lockfile)
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/pyproject.toml` — current dependency declarations
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/playwright_mcp_proxy/config.py` — location of `pydantic_settings` import and `playwright_args` default
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/.mcp.json` — second location of `@playwright/mcp@latest`
- `npm view @playwright/mcp version` — live npm query, returned `0.0.68`

### Secondary (MEDIUM confidence)
- `.planning/research/STACK.md` — prior research with per-package analysis and recommended floors
- `.planning/research/SUMMARY.md` — project-level research summary with pitfall catalogue

### Tertiary (LOW confidence)
- Training data on pytest-asyncio 0.x -> 1.x breaking changes (confirmed by lock version jump; specific behavior changes from training data, not changelog)
- Training data on pydantic-settings `class Config` deprecation timeline

---

## Metadata

**Confidence breakdown:**
- Standard stack (resolved versions): HIGH — read directly from uv.lock
- pydantic-settings missing dep: HIGH — confirmed by pyproject.toml absence + uv.lock transitive presence + config.py direct import
- @playwright/mcp current version: HIGH — live npm query returned 0.0.68
- pytest-asyncio 1.x behavior: MEDIUM — lock confirms 1.2.0, behavior details from training data
- Ruff 0.14 compatibility: HIGH — conservative rule set, lock confirms 0.14.1 resolves fine

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (npm version may change if @playwright/mcp releases a new version; re-run `npm view @playwright/mcp version` before implementing)
