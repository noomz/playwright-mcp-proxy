---
created: 2026-03-13T08:41:00.000Z
title: Investigate unintentional session expiry on proxy requests
area: api
files:
  - playwright_mcp_proxy/server/app.py
  - playwright_mcp_proxy/server/playwright_manager.py
---

## Problem

Sessions are expiring unexpectedly during normal browser automation usage. The proxy returns HTTP 400 Bad Request on `/proxy` endpoint when a `browser_click` is attempted on a valid element ref. The session appears to have expired between requests even though the user didn't close it.

Real usage log shows:
- `browser_click` with element ref "e328" returns 400 Bad Request
- User reports "Session expired again" — this is a recurring issue, not a one-off
- The session expiry forces recreation, losing browser state and context

This may be related to the 3-strike health check failure detection in `playwright_manager.py` — if the subprocess health ping fails 3 times (e.g., during a slow page load), the session could be marked as expired/closed prematurely. Or the session state tracking in `app.py` could be marking sessions closed too aggressively.

## Solution

TBD — needs investigation:
1. Check what triggers a 400 response on `/proxy` — is it session state validation?
2. Check if the health check loop (`30s ping, 3-strike`) is killing sessions during long operations
3. Check if `update_session_state` is being called with 'closed' or 'error' prematurely
4. Add better logging around session state transitions to capture the expiry trigger
5. Consider whether the auto-close logic (3 consecutive failed state captures) is too aggressive
