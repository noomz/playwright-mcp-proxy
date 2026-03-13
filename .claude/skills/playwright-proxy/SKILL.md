---
name: playwright-proxy
description: >
  Browser automation via playwright-mcp-proxy. Use this skill when navigating websites,
  capturing page content, clicking elements, typing text, or checking console logs
  through the Playwright proxy. The proxy persists all interactions in SQLite and returns
  only metadata + ref_id — always call get_content(ref_id) to retrieve actual page content.
allowed-tools:
  - playwright-proxy
  - read_file
  - write_file
  - glob
  - search_file_content
  - replace
---

## Prerequisites

The proxy server must be running before using any browser tools.

```bash
playwright-proxy-server        # start server (port 34501)
uv run playwright-proxy-server # alternative if not globally installed
playwright-proxy-ctl health    # verify server is up
```

## Core Concept: Response Policy

All browser action tools return metadata + ref_id only, never full page content. A typical response looks like:

```
✓ browser_snapshot | abc-123 | snapshot: get_content('abc-123')
```

Always call `get_content(ref_id)` after any browser action to retrieve the actual page snapshot. This is the standard workflow, not an optional pattern. Skipping `get_content` means the page content is not available to you.

## Session Lifecycle

```
create_new_session
    -> browser_navigate(url)        -> ref_id
    -> get_content(ref_id)          -> page snapshot (full, first read)
    -> browser_click(element, ref)  -> ref_id
    -> get_content(ref_id)          -> changes (empty if page unchanged)
    -> browser_type(element, ref, text) -> ref_id
    -> get_content(ref_id)          -> changes
    -> browser_close
```

Always call `create_new_session` before using any browser tool. Browser tools fail with "Error: No active session" without it.

## Tool Reference

| Tool | Parameters | Returns |
|------|-----------|---------|
| `create_new_session` | none | session_id string |
| `browser_navigate` | `url` (required) | metadata + ref_id |
| `browser_snapshot` | none | metadata + ref_id |
| `browser_click` | `element` (required), `ref` (required) | metadata + ref_id |
| `browser_type` | `element` (required), `ref` (required), `text` (required), `submit` (optional bool) | metadata + ref_id |
| `browser_console_messages` | `onlyErrors` (optional bool) | metadata + ref_id |
| `browser_close` | none | metadata + ref_id |
| `get_content` | `ref_id` (required), `search_for` (optional), `reset_cursor` (optional bool), `before_lines` (optional int), `after_lines` (optional int) | page snapshot text |
| `get_console_content` | `ref_id` (required), `level` (optional: debug/info/warn/error) | console log text |

Parameter notes:
- `element`: human-readable element description (e.g., "Submit button")
- `ref`: element reference from accessibility snapshot (e.g., "e47")
- `submit`: if true, presses Enter after typing (default: false)

## Diff Behavior

`get_content` uses hash-based change detection:

- **First read:** returns full page content, creates a diff cursor
- **Subsequent reads:** returns empty string if page unchanged, full content if changed
- **Empty response = page unchanged.** It is not an error.
- Use `reset_cursor=true` to force full content return regardless of diff state
- Console logs (via `get_console_content`) do NOT use diff — always returns full logs

## When to Snapshot vs get_content

Every proxied tool (`browser_navigate`, `browser_click`, `browser_type`) already captures a snapshot — each returns a `ref_id`. Use `get_content(ref_id)` to retrieve that snapshot.

- **`browser_snapshot`** is only needed to re-capture the page *without* performing an action (e.g., after waiting for dynamic content to load). It returns a new `ref_id`.
- **`get_content`** with the same `ref_id` uses diff: empty string = page unchanged, full content = page changed since last read.
- When you need a fresh baseline, call `browser_snapshot` to get a new `ref_id` rather than re-reading an old one.

## Content Search

`get_content` supports grep-like content filtering:

```python
get_content(ref_id="abc-123", search_for="error message")
get_content(ref_id="abc-123", search_for="login", before_lines=2, after_lines=3)
```

Use `search_for` to filter the snapshot to matching lines. `before_lines` and `after_lines` provide surrounding context (equivalent to grep -B and -A).

## Management CLI

```bash
playwright-proxy-ctl health                           # server status + subprocess health
playwright-proxy-ctl sessions list                    # all sessions
playwright-proxy-ctl sessions list --state active     # filter by state
playwright-proxy-ctl sessions clear                   # clear closed sessions (with prompt)
playwright-proxy-ctl sessions clear --state error --yes  # skip prompt
playwright-proxy-ctl db vacuum                        # compact DB (server must be stopped)
```

Session states: `active`, `closed`, `error`. The `clear` command defaults to clearing `closed` sessions.

## Test Generation Workflow

For generating Playwright test specs from browser interactions, configure `.claude-playwright.yml` with `spec_dir` and `playwright_dir`. Walk through each step using browser tools before writing test code — use `get_content` to read the page state at each step, identify element refs from the snapshot, then translate the interaction sequence into spec file syntax. Keep the session open until the user confirms the test captures the intended behavior.
