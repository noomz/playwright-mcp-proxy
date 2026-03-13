---
created: 2026-03-13T08:12:15.321Z
title: Implement list_sessions and resume_session MCP tools
area: api
files:
  - playwright_mcp_proxy/client/mcp_server.py
  - playwright_mcp_proxy/server/app.py
  - ~/.claude/skills/playwright-proxy/SKILL.md
---

## Problem

Session resumption is the project's killing feature — persistent sessions that survive server restarts differentiate playwright-mcp-proxy from vanilla Playwright MCP. The HTTP endpoints already exist in `server/app.py` (GET /sessions, POST /sessions/{id}/resume), but no MCP tool definitions expose them to clients. Users cannot discover or resume previous sessions through the MCP interface.

Phase 9 removed the phantom documentation for these tools from SKILL.md because they were never implemented as MCP tools. This todo tracks actually implementing them.

## Solution

1. Add `list_sessions` tool to `client/mcp_server.py` TOOLS list — accepts optional `state` filter parameter, calls GET /sessions endpoint
2. Add `resume_session` tool to `client/mcp_server.py` TOOLS list — accepts required `session_id`, calls POST /sessions/{id}/resume endpoint
3. Add handler logic in `handle_tool_call()` for both tools
4. Re-add Session Recovery section to SKILL.md with accurate documentation
5. Update tool count references (9 → 11)
6. Add tests for the new MCP tools
