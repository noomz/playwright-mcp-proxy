# Phase 9: Fix SKILL.md Accuracy and Close Tracking Gaps - Research

**Researched:** 2026-03-13
**Domain:** Documentation accuracy, requirement tracking, project state management
**Confidence:** HIGH

## Summary

Phase 9 is a pure documentation and tracking closure phase with no code changes to production logic. The work falls into two buckets: (1) correct SKILL.md to remove two non-existent MCP tools (`list_sessions` and `resume_session`) that were added during Phase 6 beyond the original 9-tool scope, and (2) mark all 9 pending requirements (SKIL-01..06, CHRM-01..03) as complete in REQUIREMENTS.md and update their traceability table entries.

The work was fully diagnosed by the v1.0-MILESTONE-AUDIT.md. All deliverables from Phases 6 and 8 exist and are correct — only the tracking records and one documentation inaccuracy need to be fixed. No new code or tests are required.

**Primary recommendation:** Make targeted edits to three files: `~/.claude/skills/playwright-proxy/SKILL.md` (remove 2 tool rows), `.planning/REQUIREMENTS.md` (check 9 boxes, update 9 traceability rows), and `.planning/ROADMAP.md` (mark Phase 9 progress row as Complete).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SKIL-01 | Skill file exists at `~/.claude/skills/playwright-proxy/SKILL.md` with valid YAML frontmatter (name, description, allowed-tools) | File exists and is valid — only tracking checkbox needs updating |
| SKIL-02 | All 9 MCP tools documented with parameters and return values | Exactly 9 tools exist in mcp_server.py TOOLS list; SKILL.md currently documents 11 (2 phantom tools must be removed) |
| SKIL-03 | Response policy (metadata + ref_id, then get_content) explained as standard workflow | Section exists in SKILL.md — only tracking checkbox needs updating |
| SKIL-04 | Diff behavior documented (empty = unchanged, reset_cursor for full content) | Section exists in SKILL.md — only tracking checkbox needs updating |
| SKIL-05 | playwright-proxy-ctl commands (health, sessions list/clear, db vacuum) documented | Management CLI section exists in SKILL.md — only tracking checkbox needs updating |
| SKIL-06 | Skill follows progressive disclosure and passes skill-reviewer quality criteria | Passed skill-reviewer; removing phantom tools makes it more accurate — tracking checkbox needs updating |
| CHRM-01 | Chrome measurement JSON file loads and validates with correct schema | tests/chrome_measurements.json exists with valid schema — only tracking checkbox needs updating |
| CHRM-02 | Chrome comparison test prints formatted performance table showing chrome path metrics | tests/test_chrome_comparison.py exists and passes — only tracking checkbox needs updating |
| CHRM-03 | Chrome measurements recorded for 3 scenarios with navigate and read_page metrics | 3 scenarios in chrome_measurements.json — only tracking checkbox needs updating |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python text editing | stdlib | Edit markdown files | No dependencies needed for doc edits |
| pytest | >=7.0 | Test framework (existing) | Already in project, used by all phases |

### Supporting
No additional libraries needed. This phase edits markdown files only.

### Alternatives Considered
None — this is a documentation phase with no implementation choices.

**Installation:**
No new packages required.

## Architecture Patterns

### What Exists (Ground Truth)

The authoritative source for MCP tools is `playwright_mcp_proxy/client/mcp_server.py` TOOLS list. Exactly 9 tools are defined:

```
create_new_session
get_content
get_console_content
browser_navigate
browser_snapshot
browser_click
browser_type
browser_console_messages
browser_close
```

The current SKILL.md tool reference table (lines 54-66) lists 11 tools — the 9 above plus:
- `list_sessions` (line 65) — NOT in mcp_server.py TOOLS list
- `resume_session` (line 66) — NOT in mcp_server.py TOOLS list

Both phantom tools were added during Phase 6 to document a session recovery flow. HTTP endpoints for them exist in `server/app.py` (GET /sessions, POST /sessions/{id}/resume) but no corresponding MCP tool definitions exist in the client. The audit confirms: users following SKILL.md will get tool-not-found errors.

### Files to Edit

| File | Location | Changes |
|------|----------|---------|
| `SKILL.md` | `~/.claude/skills/playwright-proxy/SKILL.md` | Remove `list_sessions` and `resume_session` rows from Tool Reference table; remove Session Recovery section (lines 115-122) |
| `REQUIREMENTS.md` | `.planning/REQUIREMENTS.md` | Check 9 boxes: SKIL-01..06 and CHRM-01..03; update 9 traceability rows to "Complete" |
| `ROADMAP.md` | `.planning/ROADMAP.md` | Update Phase 9 progress row to show "Complete" when done |

### SKILL.md Specific Changes

Lines to remove from Tool Reference table:
```markdown
| `list_sessions` | `state` (optional: active/closed/error/recoverable/stale) | list of sessions |
| `resume_session` | `session_id` (required) | resumed session confirmation |
```

Section to remove (Session Recovery, lines 115-122):
```markdown
## Session Recovery

Sessions survive server restarts. To resume a previous session:

1. `list_sessions(state="recoverable")` — find sessions that can be resumed
2. `resume_session(session_id)` — restore browser state (URL, cookies, storage)

Sessions auto-close after 3 consecutive failed state captures (e.g., the browser tab was closed by the user). Once closed, they cannot be resumed.
```

The "Session states" note on line 113 also references `recoverable` and `stale` which only matter for `list_sessions` — this line should be removed or simplified since it follows the Management CLI section.

### REQUIREMENTS.md Specific Changes

Nine checkbox lines need `[ ]` changed to `[x]`:
```markdown
- [ ] **SKIL-01** → - [x] **SKIL-01**
- [ ] **SKIL-02** → - [x] **SKIL-02**
- [ ] **SKIL-03** → - [x] **SKIL-03**
- [ ] **SKIL-04** → - [x] **SKIL-04**
- [ ] **SKIL-05** → - [x] **SKIL-05**
- [ ] **SKIL-06** → - [x] **SKIL-06**
- [ ] **CHRM-01** → - [x] **CHRM-01**
- [ ] **CHRM-02** → - [x] **CHRM-02**
- [ ] **CHRM-03** → - [x] **CHRM-03**
```

Nine traceability table rows need status updated from "Pending" to "Complete":
```markdown
| SKIL-01 | Phase 6, 9 | Pending | → | SKIL-01 | Phase 6, 9 | Complete |
...same pattern for SKIL-02..06 and CHRM-01..03...
```

### Anti-Patterns to Avoid

- **Implementing `list_sessions`/`resume_session` as MCP tools:** Out of scope per Phase 9 goal. The audit recommendation was Option 1 (fix the docs), not Option 2 (implement the tools). This is confirmed by the Phase 9 description: "Remove non-existent MCP tools from SKILL.md."
- **Editing mcp_server.py:** No code changes in this phase.
- **Removing the Session Recovery HTTP endpoints from app.py:** They are orphaned but removing them is out of scope — doc-only fix.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Checkbox updating | Custom script | Direct file edit | Three targeted string replacements — no automation needed |
| Verification | New test | Shell grep | Simple presence/absence checks sufficient |

**Key insight:** This phase is a targeted documentation patch, not a system build. The complexity is in identifying exactly which lines to change, not in how to change them.

## Common Pitfalls

### Pitfall 1: Leaving the "Session Recovery" Section
**What goes wrong:** Only removing the 2 tool rows from the table but leaving the "Session Recovery" section that references them (lines 115-122 in current SKILL.md).
**Why it happens:** Focused on the table, missed the section.
**How to avoid:** Search SKILL.md for "resume_session" and "list_sessions" after edits — both should appear 0 times.
**Warning signs:** SKILL.md still mentions `list_sessions` or `resume_session` anywhere after edits.

### Pitfall 2: Counting SKIL-02 as satisfied without fixing the tool count
**What goes wrong:** Checking the SKIL-02 box ("All 9 MCP tools documented") before removing the phantom tools, leaving SKILL.md documenting 11 tools.
**Why it happens:** Checkbox update done before SKILL.md fix.
**How to avoid:** Fix SKILL.md first, then update REQUIREMENTS.md. SKIL-02 is only satisfied when exactly 9 tools are in the table.
**Warning signs:** Tool table row count != 9 after edits.

### Pitfall 3: Partial traceability update
**What goes wrong:** Updating the 9 checkboxes but forgetting the 9 traceability table rows at the bottom of REQUIREMENTS.md (or vice versa).
**Why it happens:** Two separate locations in REQUIREMENTS.md track the same requirements.
**How to avoid:** Verify both the `### Claude Code Skill` / `### Chrome Comparison` sections AND the `## Traceability` table after edits.
**Warning signs:** Any requirement showing "Pending" in traceability while its checkbox is `[x]`.

### Pitfall 4: Forgetting the "Session states" line
**What goes wrong:** Removing the two tool rows and the Session Recovery section, but leaving line 113: `Session states: active, closed, error, recoverable, stale.` This line's only purpose was to explain states for the now-removed `list_sessions` tool.
**Why it happens:** It's in the Management CLI section, not the tool table or Session Recovery section.
**How to avoid:** Read the Management CLI section after removing the Session Recovery section — check if the session states line still makes contextual sense.

## Code Examples

### Verification after SKILL.md edits

```bash
# Confirm phantom tools are gone
grep -c "list_sessions\|resume_session" ~/.claude/skills/playwright-proxy/SKILL.md
# Expected: 0

# Confirm exactly 9 tools in table (header + 9 rows = 10 pipe-delimited lines starting with | `)
grep -c "^| \`" ~/.claude/skills/playwright-proxy/SKILL.md
# Expected: 9
```

### Verification after REQUIREMENTS.md edits

```bash
# Confirm all target requirements are checked
grep -E "\[x\] \*\*(SKIL|CHRM)" .planning/REQUIREMENTS.md
# Expected: 9 lines

# Confirm no remaining unchecked SKIL/CHRM requirements
grep -E "\[ \] \*\*(SKIL|CHRM)" .planning/REQUIREMENTS.md
# Expected: 0 lines (empty output)

# Confirm traceability shows Complete for all 27
grep "Pending" .planning/REQUIREMENTS.md
# Expected: 0 lines (empty output)
```

## State of the Art

| Old State | Current State (Phase 9 Goal) |
|-----------|------------------------------|
| SKILL.md lists 11 tools (2 phantom) | SKILL.md lists exactly 9 tools (matches mcp_server.py) |
| 9 requirements unchecked in REQUIREMENTS.md | All 27 requirements checked |
| Traceability shows "Pending" for 9 items | Traceability shows "Complete" for all 27 |
| Session Recovery section documents broken flow | Section removed (flow unreachable via MCP) |

## Open Questions

1. **Session states line in Management CLI section (line 113)**
   - What we know: `Session states: active, closed, error, recoverable, stale.` — this line exists under the ctl section, after the command table
   - What's unclear: Whether to keep it (it describes valid session states for `--state` filter) or remove it (it's only useful with `list_sessions` which is being removed)
   - Recommendation: Keep the line but narrow it. The `sessions list --state` flag still accepts these values even without the MCP tool. The ctl `sessions clear` also uses state. Keep as-is or simplify to only states relevant to ctl commands.

2. **ROADMAP.md Phase 9 progress row**
   - What we know: Row exists for Phase 9 with "0/1" and "Planned"
   - What's unclear: Should the Phase 9 plan row in the ROADMAP plans list also be updated?
   - Recommendation: The planner should update Phase 9's progress row to "1/1 | Complete | 2026-03-13" as part of the PLAN tasks.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (>=7.0) |
| Config file | pyproject.toml (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/test_database.py tests/test_diff.py -x -q` |
| Full suite command | `uv run pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SKIL-01 | SKILL.md exists with valid frontmatter | manual-only | `test -f ~/.claude/skills/playwright-proxy/SKILL.md && head -5 ~/.claude/skills/playwright-proxy/SKILL.md` | N/A (file check) |
| SKIL-02 | Exactly 9 tools documented | manual-only | `grep -c "^\| \\\`" ~/.claude/skills/playwright-proxy/SKILL.md` | N/A (count check) |
| SKIL-03 | Response policy section exists | manual-only | `grep -q "Response Policy" ~/.claude/skills/playwright-proxy/SKILL.md` | N/A |
| SKIL-04 | Diff behavior documented | manual-only | `grep -q "Diff Behavior" ~/.claude/skills/playwright-proxy/SKILL.md` | N/A |
| SKIL-05 | ctl commands documented | manual-only | `grep -q "playwright-proxy-ctl health" ~/.claude/skills/playwright-proxy/SKILL.md` | N/A |
| SKIL-06 | No phantom tools remain | manual-only | `grep -c "list_sessions\|resume_session" ~/.claude/skills/playwright-proxy/SKILL.md` = 0 | N/A |
| CHRM-01 | JSON loads with valid schema | unit | `uv run pytest tests/test_chrome_comparison.py -k "test_chrome_measurements_schema" -x` | ✅ |
| CHRM-02 | Comparison table prints | unit | `uv run pytest tests/test_chrome_comparison.py -k "test_chrome_comparison_table" -x` | ✅ |
| CHRM-03 | 3 scenarios with measurements | unit | `uv run pytest tests/test_chrome_comparison.py -m chrome_comparison -x` | ✅ |

**Note:** SKIL-01..06 are documentation requirements with no automated test coverage. Verification is by shell command inspection of the file content. CHRM-01..03 are already covered by existing tests in `tests/test_chrome_comparison.py` — no new tests needed.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_chrome_comparison.py -m chrome_comparison -q`
- **Per wave merge:** `uv run pytest -q`
- **Phase gate:** Full suite green (currently 93 tests) before `/gsd:verify-work`

### Wave 0 Gaps
None — existing test infrastructure covers all phase requirements. No new test files needed.

## Sources

### Primary (HIGH confidence)
- Direct file read of `playwright_mcp_proxy/client/mcp_server.py` TOOLS list — canonical tool list (9 tools confirmed)
- Direct file read of `~/.claude/skills/playwright-proxy/SKILL.md` — 11 tools in table (2 phantom confirmed)
- Direct file read of `.planning/v1.0-MILESTONE-AUDIT.md` — authoritative gap analysis
- Direct file read of `.planning/REQUIREMENTS.md` — 9 unchecked requirements confirmed

### Secondary (MEDIUM confidence)
- `.planning/phases/06-create-claude-code-skill-for-playwright-proxy-tools/06-01-SUMMARY.md` — confirms what Phase 6 actually delivered
- `.planning/phases/08-add-new-perf-comparison-results-between-claude-in-chrome/08-01-SUMMARY.md` — confirms what Phase 8 delivered
- `.planning/ROADMAP.md` — Phase 9 description and success criteria

### Tertiary (LOW confidence)
None needed — all findings verified from source files.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependencies, pure doc edits
- Architecture: HIGH — exact files and line ranges identified from direct file inspection
- Pitfalls: HIGH — identified from audit report + direct SKILL.md reading

**Research date:** 2026-03-13
**Valid until:** Indefinitely (static documentation, not a moving ecosystem target)
