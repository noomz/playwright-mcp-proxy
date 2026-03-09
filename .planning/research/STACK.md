# Technology Stack

**Project:** Playwright MCP Proxy — Modernization & Tech Debt
**Researched:** 2026-03-09

## Recommended Stack

### Core Framework

| Technology | Current Min | Resolved (uv.lock) | Recommended Min | Purpose | Why |
|------------|-------------|---------------------|-----------------|---------|-----|
| fastapi | >=0.115.0 | 0.119.1 | >=0.119.0 | HTTP server | Major version jump from 0.115 to 0.119. FastAPI 0.119+ includes Starlette 0.48 compatibility, improved lifespan handling, and better Pydantic v2 integration. Bump minimum to match resolved. |
| uvicorn | >=0.32.0 | 0.38.0 | >=0.34.0 | ASGI server | 0.32 -> 0.38 is a significant jump. Uvicorn 0.34+ added improved shutdown handling and HTTP/2 support. 0.38 includes Python 3.14 compatibility fixes. |
| aiosqlite | >=0.20.0 | 0.21.0 | >=0.21.0 | Async SQLite | Minor bump. 0.21.0 (Feb 2025) is likely the final release — aiosqlite is feature-complete. Pin to 0.21.0 exactly. |
| mcp | >=1.0.0 | 1.18.0 | >=1.15.0 | MCP SDK | **CRITICAL UPDATE.** 1.0 -> 1.18 is 18 minor versions. The MCP SDK has evolved rapidly. 1.18.0 pulls in pydantic-settings, httpx-sse, starlette as dependencies. The Server API used (`mcp.server.Server`, `mcp.server.stdio.stdio_server`, `mcp.types.TextContent/Tool`) appears stable but should be verified. Set minimum to >=1.15.0 to ensure recent protocol features. |
| httpx | >=0.27.0 | 0.28.1 | >=0.28.0 | HTTP client | 0.27 -> 0.28 is a minor bump. httpx 0.28 dropped the `sniffio` requirement for auto-detecting async library. No breaking API changes for this project's usage. |
| pydantic | >=2.9.0 | 2.12.3 | >=2.10.0 | Data validation | 2.9 -> 2.12 adds `typing-inspection` as new dependency, performance improvements. 2.10+ includes important fixes for Python 3.13/3.14 compatibility. No breaking changes within Pydantic 2.x line. |
| pydantic-settings | **MISSING** | 2.11.0 (transitive) | >=2.8.0 | Config management | **BUG: Not declared in pyproject.toml** but used directly in `config.py` and pulled in transitively by `mcp`. Must be added as explicit dependency. |

### Infrastructure

| Technology | Current Min | Resolved (uv.lock) | Recommended Min | Purpose | Why |
|------------|-------------|---------------------|-----------------|---------|-----|
| python-dotenv | >=1.0.0 | 1.1.1 | >=1.0.0 | Env file loading | Stable, minimal changes. 1.1.1 is a bugfix. Keep current minimum. |
| psutil | >=6.1.0 | 7.1.1 | >=6.1.0 | Process management | 6.1 -> 7.1 is a major version bump. psutil 7.x improved macOS/ARM support. No breaking API changes for basic process management. Keep minimum loose since usage is minimal. |

### Dev Dependencies

| Technology | Current Min | Resolved (uv.lock) | Recommended Min | Purpose | Why |
|------------|-------------|---------------------|-----------------|---------|-----|
| pytest | >=8.3.0 | 8.4.2 | >=8.3.0 | Test runner | 8.4 adds `pygments` as dependency for better output. No breaking changes. Keep current min. |
| pytest-asyncio | >=0.24.0 | 1.2.0 | >=1.0.0 | Async tests | **BREAKING CHANGE.** 0.24 -> 1.0 is a major version change. pytest-asyncio 1.0+ changed default behavior: `asyncio_mode = "auto"` is now the default (project already uses this). The `@pytest.mark.asyncio` decorator behavior changed. Must verify tests work with 1.x. Set min to >=1.0.0. |
| pytest-cov | >=6.0.0 | 7.0.0 | >=6.0.0 | Coverage | 7.0 includes `pluggy` as explicit dependency. No breaking changes for usage. Keep current min. |
| ruff | >=0.7.0 | 0.14.1 | >=0.9.0 | Linter/formatter | 0.7 -> 0.14 is a massive jump. Ruff adds new rules and may flag new issues. 0.9+ has stabilized rule sets. The project's selected rules (E, F, I, N, W) are stable across versions. |

### Build System

| Technology | Role | Notes |
|------------|------|-------|
| hatchling | Build backend | Declared in `[build-system]` requires. Not version-pinned in lock (build dependency). Hatchling is stable and backward-compatible. No action needed. |

### External Subprocess

| Technology | Current | Recommended | Purpose | Why |
|------------|---------|-------------|---------|-----|
| @playwright/mcp | @latest (unpinned) | Pin to specific version | Playwright MCP server | **RISK: `@latest` means any `npx` invocation could pull a breaking version.** Could not verify exact latest npm version (web tools unavailable). Pin to the version currently working in your environment (`npm view @playwright/mcp version` to check). |

## Critical Findings

### 1. Missing `pydantic-settings` dependency (HIGH confidence)

`pydantic-settings` is imported in `config.py` but not listed in `pyproject.toml` dependencies. It works today because `mcp` pulls it in transitively, but this is fragile:
- If `mcp` ever drops the dependency, the app breaks
- Makes the dependency graph misleading

**Action:** Add `"pydantic-settings>=2.8.0"` to `[project.dependencies]`.

### 2. pytest-asyncio major version jump (HIGH confidence)

pytest-asyncio went from 0.x to 1.x. Key changes in 1.0:
- `asyncio_mode = "auto"` became the default (project already uses this, so no issue)
- Fixture scoping behavior changed — async fixtures now properly respect scope
- The `@pytest.mark.asyncio` decorator is no longer needed in auto mode (already the case)

The project config already has `asyncio_mode = "auto"`, so the 1.0 upgrade should be smooth. Tests should still be verified.

### 3. MCP SDK rapid evolution (MEDIUM confidence)

The MCP SDK went from 1.0 to 1.18 in a short time. The project uses a small surface area:
- `mcp.server.Server` — core server class
- `mcp.server.stdio.stdio_server` — stdio transport
- `mcp.types.TextContent`, `mcp.types.Tool` — type definitions

These are foundational APIs unlikely to break, but the SDK now bundles many more dependencies (httpx-sse, starlette, uvicorn, jsonschema). The minimum should be bumped to avoid compatibility issues with older versions that may not include needed fixes.

### 4. Ruff version gap (LOW risk, HIGH confidence)

Ruff 0.7 -> 0.14 is a large jump but the project uses a conservative rule set (E, F, I, N, W with E501 ignored). New Ruff versions may:
- Format code slightly differently
- Flag new issues under existing rule categories
- Have different default behaviors

Run `ruff check .` after upgrade to verify no new violations.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Async SQLite | aiosqlite | databases + SQLAlchemy | Overkill for single-file SQLite. aiosqlite is simpler, project already uses raw SQL. |
| HTTP client | httpx | aiohttp | httpx is already used, lighter, and the MCP SDK depends on it too. |
| Config | pydantic-settings | python-decouple | pydantic-settings integrates natively with Pydantic models already used in config.py. |
| Linter | ruff | flake8 + isort + black | Ruff replaces all three in one tool. Already in use. No reason to switch. |
| Build | hatchling | setuptools | Hatchling is modern, fast, and already configured. No reason to change. |

## Recommended pyproject.toml Changes

```toml
[project]
dependencies = [
    "fastapi>=0.119.0",
    "uvicorn>=0.34.0",
    "aiosqlite>=0.21.0",
    "mcp>=1.15.0",
    "httpx>=0.28.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.8.0",   # ADD: was missing, used in config.py
    "python-dotenv>=1.0.0",
    "psutil>=6.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=1.0.0",      # BUMP: major version change
    "pytest-cov>=6.0.0",
    "ruff>=0.9.0",                # BUMP: significant feature additions
]
```

## Installation

```bash
# Update lockfile after pyproject.toml changes
uv lock

# Install with updated dependencies
uv pip install -e ".[dev]"

# Verify no ruff violations
uv run ruff check .

# Verify tests pass
uv run pytest
```

## Confidence Assessment

| Finding | Confidence | Basis |
|---------|------------|-------|
| Package versions from uv.lock | HIGH | Direct reading of resolved lockfile |
| pydantic-settings missing | HIGH | Verified in pyproject.toml vs config.py imports |
| pytest-asyncio breaking changes | MEDIUM | Based on training data knowledge of 0.x -> 1.x transition; version jump confirmed in lock |
| MCP SDK API stability | MEDIUM | Small API surface verified in code, but could not check MCP changelog |
| @playwright/mcp npm version | LOW | Could not verify (web tools unavailable); recommend running `npm view @playwright/mcp version` locally |
| Ruff compatibility | HIGH | Conservative rule set, lockfile confirms 0.14.1 resolves fine |

## Sources

- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/uv.lock` — All resolved package versions (authoritative, from PyPI)
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/pyproject.toml` — Current dependency specifications
- `/Users/noomz/Projects/Opensources/playwright-mcp-proxy/.planning/codebase/STACK.md` — Current stack analysis
- Training data knowledge for breaking change analysis (MEDIUM confidence, May 2025 cutoff)
