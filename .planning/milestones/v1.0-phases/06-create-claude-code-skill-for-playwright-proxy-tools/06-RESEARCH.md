# Phase 06: Create Claude Code Skill for Playwright-Proxy Tools - Research

**Researched:** 2026-03-11
**Domain:** Claude Code skill authoring, playwright-mcp-proxy tool surface
**Confidence:** HIGH

## Summary

This phase creates a Claude Code skill for the `playwright-mcp-proxy` tool set. A skill is a structured markdown document placed in `~/.claude/skills/<skill-name>/SKILL.md` that teaches Claude how to use a specific tool or accomplish a domain task. Skills use YAML frontmatter for metadata and a markdown body for workflow instructions.

An existing `playwright-proxy` skill already exists at `~/.claude/skills/playwright-proxy/SKILL.md`. It is currently minimal: it describes only the test-generation workflow (converting human instructions into Playwright spec files) and lists `allowed-tools` but does not cover the proxy's core capabilities — sessions, diff-based content retrieval, console log access, or the ctl management tool. Phase 6 rewrites this skill to be a complete, production-quality reference for using playwright-mcp-proxy as a browser automation tool from within Claude Code.

**Primary recommendation:** Rewrite `~/.claude/skills/playwright-proxy/SKILL.md` in-place, expanding it from a test-generator-only skill into a complete reference for the entire playwright-proxy tool surface, following the progressive-disclosure pattern seen in other skills in this project's ecosystem.

## Standard Stack

### Core
| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| SKILL.md | — | Skill definition file (always this name) | Convention enforced by Claude Code skill loader |
| YAML frontmatter | — | Machine-readable metadata | Required: `name`, `description`, optional: `allowed-tools`, `vm0_secrets`, `vm0_vars` |
| Markdown body | — | Human-readable workflow instructions | Claude Code reads this as instructions at skill activation |

### Supporting Files (optional but observed in ecosystem)
| File/Dir | Purpose | When to Use |
|----------|---------|-------------|
| `references/*.md` | Deep-dive reference docs | When SKILL.md body would exceed ~130 lines of actionable content |
| `scripts/` | Helper scripts | When the skill requires runnable code |
| `LICENSE.txt` | Licensing | For skills with proprietary content |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single SKILL.md | Multi-file with references/ | Only needed if body exceeds manageable size; keep lean for now |
| Rewrite in-place | New skill directory | In-place is correct — skill already exists at `playwright-proxy` |

## Architecture Patterns

### Skill Directory Structure (this project)
```
~/.claude/skills/playwright-proxy/
└── SKILL.md          # Single-file skill (sufficient for this domain)
```

More complex skills optionally add:
```
~/.claude/skills/macos-cleaner/
├── SKILL.md
├── references/
│   ├── cleanup_targets.md
│   ├── mole_integration.md
│   └── safety_rules.md
└── scripts/
    ├── analyze_caches.py
    └── ...
```

### SKILL.md YAML Frontmatter Pattern
```yaml
---
name: playwright-proxy
description: >
  [Clear description of WHAT this skill does and WHEN to use it.
   One or two sentences. Triggers the skill to load.]
allowed-tools:
  - playwright-proxy       # The MCP tool name
  - read_file
  - write_file
  - glob
  - search_file_content
  - replace
---
```

### Progressive Disclosure Pattern (HIGH confidence — observed across all ecosystem skills)
1. **Frontmatter** (always loaded): name + description trigger when skill is relevant
2. **SKILL.md body** (loaded when skill activated): Workflow, tool reference, examples
3. **references/*.md** (loaded on demand): Deep API docs, edge cases, advanced patterns

### Mental Model Language Pattern
Skills use canonical, declarative language:
- "Use `playwright-proxy` to navigate and interact with browser" (correct)
- "You can optionally use this new playwright feature" (avoid)

The body describes the workflow as the standard operating procedure, not an option.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Session management | Custom session tracking logic in skill | `create_new_session` tool | Already implemented in MCP server |
| Content retrieval | Trying to read snapshot from proxy response | `get_content(ref_id)` | Proxy returns metadata+ref_id only by design |
| Diff tracking | Manual change detection | `get_content` with diff cursor | Built-in hash-based diff in Phase 2 |
| Console log access | Parsing raw browser output | `get_console_content(ref_id)` | Normalized logs stored in SQLite |
| Server management | Direct subprocess interaction | `playwright-proxy-ctl` | Phase 5 CLI handles health/sessions/vacuum |

## playwright-proxy Tool Surface (what the skill must document)

### Tool Inventory (from `mcp_server.py`)

| Tool | Purpose | Returns |
|------|---------|---------|
| `create_new_session` | Start a new browser session | session_id string |
| `browser_navigate` | Navigate to URL | metadata + ref_id |
| `browser_snapshot` | Capture accessibility tree | metadata + ref_id |
| `browser_click` | Click an element | metadata + ref_id |
| `browser_type` | Type text into element | metadata + ref_id |
| `browser_console_messages` | Get console messages | metadata + ref_id |
| `browser_close` | Close the browser | metadata + ref_id |
| `get_content` | Retrieve page snapshot (with diff) | page snapshot text |
| `get_console_content` | Retrieve console logs | log text |

### Response Policy (Phase 1 — critical for skill correctness)
All browser action tools return only:
```
✓ browser_snapshot | <ref_id> | snapshot: get_content('<ref_id>')
```
The full snapshot or console data is never in the proxy response. The skill MUST teach:
1. Call a browser action tool → receive `ref_id`
2. Call `get_content(ref_id)` → receive actual page content
3. Call `get_console_content(ref_id)` → receive console logs

### Diff Behavior (Phase 2 — critical for efficiency)
`get_content` returns empty string if page has not changed since last call:
- First read: full content returned, cursor created
- Subsequent reads: empty if unchanged, full content if changed
- `reset_cursor=true`: forces full content return
- `search_for` parameter: filters content (like grep)
- `before_lines`/`after_lines`: context lines around match (like grep -B/-A)

### Session Lifecycle Pattern
```
create_new_session
    ↓
browser_navigate(url)  → ref_id_1
get_content(ref_id_1)  → page snapshot
    ↓
browser_click(...)     → ref_id_2
get_content(ref_id_2)  → changed content (or empty if unchanged)
    ↓
browser_close          → ref_id_3
```

## Common Pitfalls

### Pitfall 1: Trying to Read Content from Action Response
**What goes wrong:** Caller tries to use the proxy response text as page content.
**Why it happens:** Standard Playwright MCP returns full content; this proxy does not.
**How to avoid:** Always call `get_content(ref_id)` after any browser action that might produce a snapshot.
**Warning signs:** Response text looks like `✓ browser_snapshot | abc123 | snapshot: get_content('abc123')`.

### Pitfall 2: Ignoring Empty get_content Response
**What goes wrong:** Caller assumes empty string means an error or empty page.
**Why it happens:** Diff cursor returned empty because page hasn't changed.
**How to avoid:** If `get_content` returns empty and no error, the page is unchanged. Use `reset_cursor=true` if full content is needed.

### Pitfall 3: Calling Browser Tools Without a Session
**What goes wrong:** Tool returns "Error: No active session. Call create_new_session first."
**Why it happens:** `current_session_id` is None; session was never created or was lost.
**How to avoid:** Always call `create_new_session` at the start of a workflow.

### Pitfall 4: Skill Describes Test Generation Only
**What goes wrong:** Skill doesn't teach how to do general browser automation, only Playwright spec file generation.
**Why it happens:** Original SKILL.md was written for a single narrow use case.
**How to avoid:** Phase 6 rewrites the skill to cover the full tool surface.

### Pitfall 5: Skill Body Exceeds Manageable Size
**What goes wrong:** SKILL.md becomes too long, hard to maintain, loses focus.
**Why it happens:** Adding every edge case to SKILL.md instead of references/.
**How to avoid:** Keep core workflow in SKILL.md (~100-150 lines), move deep reference to `references/` files. Load them on demand.

## Code Examples

### Minimal Viable Workflow (from actual tool interface)
```
# Step 1: start session
create_new_session → "Created session: abc-123"

# Step 2: navigate
browser_navigate(url="https://example.com")
→ "✓ browser_navigate | ref_1 | snapshot: get_content('ref_1')"

# Step 3: read content
get_content(ref_id="ref_1")
→ [full accessibility tree text]

# Step 4: interact
browser_click(element="Submit button", ref="e47")
→ "✓ browser_click | ref_2"

# Step 5: check for changes (diff)
get_content(ref_id="ref_2")
→ "" (empty = no change) OR [new content]

# Step 6: search within content
get_content(ref_id="ref_2", search_for="error", before_lines=2, after_lines=2)
→ [matching lines with context]
```

### ctl Commands (Phase 5 — document in skill)
```bash
playwright-proxy-ctl health               # check server status
playwright-proxy-ctl sessions list        # list all sessions
playwright-proxy-ctl sessions list --state active
playwright-proxy-ctl sessions clear       # clear closed sessions (with confirmation)
playwright-proxy-ctl sessions clear --state error --yes
playwright-proxy-ctl db vacuum            # compact DB (server must be stopped)
```

## Current State of Existing Skill

The existing `~/.claude/skills/playwright-proxy/SKILL.md` (SKILL.md only, no subdirectories):
- **Covers:** Test generation workflow, `.claude-playwright.yml` config file, 6-step workflow for spec generation
- **Missing:** Session lifecycle, diff behavior, `get_content`/`get_console_content` usage, `playwright-proxy-ctl` commands, the actual tool names and parameters, response policy explanation
- **Frontmatter issue:** `allowed-tools: [playwright-proxy]` — lists the MCP tool by one name, but actual tool names are `create_new_session`, `browser_navigate`, etc. (the `playwright-proxy` entry likely refers to the MCP server registration name, which is correct)
- **Status:** Needs complete rewrite to be useful as a general-purpose browser automation skill

## Skill Quality Criteria (from skill-reviewer)

The `skill-reviewer` skill (also in this ecosystem) defines 10 quality criteria:
1. Progressive Disclosure — metadata/instructions/resources properly separated
2. Mental Model Shift — describes as canonical approach, not "new feature"
3. Degree of Freedom — matches instructions to autonomy level
4. SKILL.md Conciseness — lean, actionable, purpose-driven
5. Safety & Failure Handling — guardrails and recovery steps
6. Resource Hygiene — references current, minimal, discoverable
7. Consistency — terminology clear and unambiguous
8. Testing Guidance — verification steps or examples
9. Ownership (optional) — known limitations documented
10. Tight Scope — focused purpose, no feature creep

The rewritten skill should pass all 10 criteria.

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| Skill covers test generation only | Skill covers full tool surface | Can use skill for all browser automation |
| No session lifecycle documentation | Explicit create → use → close flow | Eliminates "no active session" errors |
| No diff behavior documentation | Documents empty-means-unchanged contract | Prevents false "page is empty" misreadings |
| No ctl documentation | Documents all 4 ctl commands | Enables operational management from skill |

## Open Questions

1. **Should the skill reference a `.claude-playwright.yml` config file?**
   - What we know: Existing skill uses this for test spec paths
   - What's unclear: Is this still relevant for general browser automation?
   - Recommendation: Keep in a "Test Generation" section for backward compat, but make it secondary to the general workflow

2. **Should the skill include MCP server startup instructions?**
   - What we know: Server runs via `uv run playwright-proxy-server` or `playwright-proxy-server`
   - What's unclear: Prerequisite vs. out-of-scope?
   - Recommendation: Add a "Prerequisites" section with one-liner start command and `ctl health` check

3. **Does the skill need a `references/` directory?**
   - What we know: Other complex skills use references/ for deep docs
   - What's unclear: Will SKILL.md body for this domain exceed manageable size?
   - Recommendation: Start with single SKILL.md. If body exceeds ~150 lines cleanly structured, extract a `references/tool-reference.md`.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/test_database.py -x` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

This phase produces a documentation artifact (SKILL.md), not executable code. There are no unit tests to write for the skill file itself. However, the skill can be smoke-tested by:

| Requirement | Behavior | Test Type | Notes |
|-------------|----------|-----------|-------|
| Skill file exists at correct path | `~/.claude/skills/playwright-proxy/SKILL.md` is valid markdown with correct frontmatter | Manual verification | File existence check |
| Skill covers all tools | All 9 tools documented | Manual review | Cross-check against `mcp_server.py` TOOLS list |
| Skill passes quality criteria | All 10 skill-reviewer criteria pass | Manual review | Apply skill-reviewer checklist |

### Sampling Rate
- **Per task commit:** No automated test command (documentation phase)
- **Per wave merge:** Manual quality checklist review
- **Phase gate:** Skill file exists at `~/.claude/skills/playwright-proxy/SKILL.md` with complete content

### Wave 0 Gaps
None — this phase produces a skill file, not executable code. No test infrastructure gaps.

## Sources

### Primary (HIGH confidence)
- Direct file inspection: `~/.claude/skills/playwright-proxy/SKILL.md` — existing skill content
- Direct file inspection: `playwright_mcp_proxy/client/mcp_server.py` — authoritative tool list and response format
- Direct file inspection: `playwright_mcp_proxy/ctl/commands.py` — ctl command surface
- Direct inspection of skills ecosystem: `~/.claude/skills/*/SKILL.md` — all 8 skills examined for patterns
- Direct inspection: `~/.claude/skills/skill-reviewer/SKILL.md` — 10-point quality criteria

### Secondary (MEDIUM confidence)
- `CLAUDE.md` project instructions — architecture, tool names, design decisions
- `.planning/ROADMAP.md` — phase context and dependency chain

### Tertiary (LOW confidence)
- None required — all domain knowledge is local to the repository

## Metadata

**Confidence breakdown:**
- Skill format/structure: HIGH — examined 8 existing skills directly
- Tool surface coverage: HIGH — read mcp_server.py TOOLS list directly
- Response policy: HIGH — read from mcp_server.py handle_tool_call()
- Diff behavior: HIGH — documented in CLAUDE.md and Phase 2 requirements
- Quality criteria: HIGH — skill-reviewer SKILL.md read directly

**Research date:** 2026-03-11
**Valid until:** 2026-06-11 (stable domain — skill format is not version-sensitive)
