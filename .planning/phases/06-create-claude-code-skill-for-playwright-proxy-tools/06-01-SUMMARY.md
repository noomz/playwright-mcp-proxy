---
phase: 06-create-claude-code-skill-for-playwright-proxy-tools
plan: 01
subsystem: documentation
tags: [claude-code, skill, mcp-tools, documentation]

requires:
  - phase: 01-dependency-hygiene
    provides: stable dependency baseline
  - phase: 02-bug-fixes
    provides: correct tool behavior for documentation
  - phase: 05-cli-management-tool-playwright-proxy-ctl
    provides: ctl commands to document
---

<one_liner>
Rewrote SKILL.md from test-generation-only to complete playwright-proxy reference covering all 9 tools, response policy, diff behavior, and ctl commands.
</one_liner>

<what_was_done>

## Changes

Replaced the narrow test-generation-focused SKILL.md with a comprehensive browser automation skill:

- **YAML frontmatter**: `name: playwright-proxy` with description and allowed-tools
- **Response policy**: Documents the ref_id → get_content flow as the standard workflow
- **Session lifecycle**: Visual flow from create_new_session through browser_close
- **Tool reference table**: All 9 MCP tools with parameters and return values
- **Diff behavior**: Hash-based change detection, empty = unchanged, reset_cursor explained
- **Content search**: grep-like filtering with before_lines/after_lines context
- **Management CLI**: All playwright-proxy-ctl commands (health, sessions list/clear, db vacuum)
- **Test generation workflow**: Preserved backward-compatible section for spec generation

File: `.claude/skills/playwright-proxy/SKILL.md` (107 lines, under 130-line target)

</what_was_done>

<verification>

### Automated checks
- Skill file exists at `.claude/skills/playwright-proxy/SKILL.md`: PASS
- Frontmatter contains `name: playwright-proxy`: PASS
- All 9 tools referenced (27 mentions across file): PASS
- Body under 130 lines (107 lines): PASS

### Must-haves verified
- [x] Skill file exists with valid YAML frontmatter
- [x] All 9 MCP tools documented with parameters and return values
- [x] Response policy (ref_id -> get_content flow) clearly explained
- [x] Diff behavior (empty = unchanged, reset_cursor for full) documented
- [x] playwright-proxy-ctl commands (health, sessions list/clear, db vacuum) documented
- [x] Progressive disclosure pattern followed

</verification>
