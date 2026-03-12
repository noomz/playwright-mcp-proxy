"""Session state capture and restoration for Phase 7."""

import json
import logging
from datetime import datetime
from typing import Optional

from ..models.database import SessionSnapshot
from .playwright_manager import PlaywrightManager

logger = logging.getLogger(__name__)


class SessionStateManager:
    """Manages session state capture and restoration."""

    def __init__(self, playwright_manager: PlaywrightManager):
        """
        Initialize session state manager.

        Args:
            playwright_manager: Playwright manager instance for browser communication
        """
        self.playwright = playwright_manager

    async def capture_state(self, session_id: str) -> Optional[SessionSnapshot]:
        """
        Capture current browser state for a session.

        Extracts in a single combined RPC:
        - Current URL
        - Cookies
        - localStorage
        - sessionStorage
        - Viewport size

        Each property has its own try/catch in the JS function so a SecurityError
        on one property does not prevent the others from being captured.

        Args:
            session_id: Session ID to capture state for

        Returns:
            SessionSnapshot with captured state, or None if capture fails
        """
        try:
            # Single combined browser_evaluate RPC (PERF-02)
            combined_js = """() => {
    const s = {};
    try { s.url = window.location.href; } catch(e) { s.url = null; }
    try { s.cookies = document.cookie; } catch(e) { s.cookies = ""; }
    try { s.localStorage = JSON.stringify(localStorage); } catch(e) { s.localStorage = "{}"; }
    try { s.sessionStorage = JSON.stringify(sessionStorage); } catch(e) { s.sessionStorage = "{}"; }
    try { s.viewport = JSON.stringify({width: window.innerWidth, height: window.innerHeight}); } catch(e) { s.viewport = "{}"; }
    return s;
}"""

            result = await self.playwright.send_request(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {
                        "function": combined_js,
                    },
                },
            )

            raw_text = self._extract_evaluate_result(result)
            if not raw_text:
                logger.debug(f"Empty response for session {session_id} (tab likely closed)")
                return None
            try:
                state = json.loads(raw_text)
            except json.JSONDecodeError:
                logger.debug(f"Non-JSON response for session {session_id} (tab likely closed): {raw_text[:100]}")
                return None

            # Extract each property with fallbacks for null (partial failure)
            current_url = state.get("url") or ""
            cookies_str = state.get("cookies") or ""
            local_storage_raw = state.get("localStorage")
            session_storage_raw = state.get("sessionStorage")
            viewport_raw = state.get("viewport")

            # Normalise nulls from JS try/catch fallbacks
            local_storage = local_storage_raw if local_storage_raw is not None else "{}"
            session_storage = session_storage_raw if session_storage_raw is not None else "{}"
            viewport = viewport_raw if viewport_raw is not None else "{}"

            # Parse cookies string into structured JSON
            cookies_json = json.dumps(self._parse_cookie_string(cookies_str))

            # Create snapshot
            snapshot = SessionSnapshot(
                session_id=session_id,
                current_url=current_url,
                cookies=cookies_json,
                local_storage=local_storage,
                session_storage=session_storage,
                viewport=viewport,
                snapshot_time=datetime.now(),
            )

            logger.info(f"Captured state for session {session_id}: URL={current_url}")
            return snapshot

        except Exception as e:
            logger.error(f"Failed to capture state for session {session_id}: {e}")
            return None

    def _extract_evaluate_result(self, result: dict) -> str:
        """
        Extract the actual result from browser_evaluate response.

        Playwright MCP returns results in the format:
        {
            "content": [
                {"type": "text", "text": "<actual result>"}
            ]
        }

        Args:
            result: Raw result from browser_evaluate

        Returns:
            Extracted string result
        """
        if "content" in result and len(result["content"]) > 0:
            return result["content"][0].get("text", "")
        return ""

    def _parse_cookie_string(self, cookie_str: str) -> list[dict]:
        """
        Parse document.cookie string into structured format.

        document.cookie returns: "name1=value1; name2=value2"

        Args:
            cookie_str: Cookie string from document.cookie

        Returns:
            List of cookie objects with name and value
        """
        if not cookie_str:
            return []

        cookies = []
        for part in cookie_str.split("; "):
            if "=" in part:
                name, value = part.split("=", 1)
                cookies.append({"name": name, "value": value})
        return cookies

    async def restore_state(self, snapshot: SessionSnapshot) -> bool:
        """
        Restore browser state from a snapshot.

        Uses json.dumps() for all user data embedded in JS function strings to
        prevent JS injection from values containing quotes, backslashes, or
        newlines (SECR-01).

        Args:
            snapshot: SessionSnapshot to restore

        Returns:
            True if restoration succeeded, False otherwise
        """
        try:
            # 1. Navigate to saved URL
            if snapshot.current_url:
                await self.playwright.send_request(
                    "tools/call",
                    {
                        "name": "browser_navigate",
                        "arguments": {"url": snapshot.current_url},
                    },
                )

            # 2. Restore localStorage (injection-safe via json.dumps)
            if snapshot.local_storage:
                storage_data = json.loads(snapshot.local_storage)
                for key, value in storage_data.items():
                    await self.playwright.send_request(
                        "tools/call",
                        {
                            "name": "browser_evaluate",
                            "arguments": {
                                "function": f"() => localStorage.setItem({json.dumps(key)}, {json.dumps(value)})",
                            },
                        },
                    )

            # 3. Restore sessionStorage (injection-safe via json.dumps)
            if snapshot.session_storage:
                storage_data = json.loads(snapshot.session_storage)
                for key, value in storage_data.items():
                    await self.playwright.send_request(
                        "tools/call",
                        {
                            "name": "browser_evaluate",
                            "arguments": {
                                "function": f"() => sessionStorage.setItem({json.dumps(key)}, {json.dumps(value)})",
                            },
                        },
                    )

            # 4. Restore cookies (injection-safe via json.dumps)
            # Note: Limited to document.cookie — real implementation should use context.addCookies()
            if snapshot.cookies:
                cookies_list = json.loads(snapshot.cookies)
                for cookie in cookies_list:
                    cookie_literal = json.dumps(f"{cookie['name']}={cookie['value']}")
                    await self.playwright.send_request(
                        "tools/call",
                        {
                            "name": "browser_evaluate",
                            "arguments": {
                                "function": f"() => document.cookie = {cookie_literal}",
                            },
                        },
                    )

            # 5. Restore viewport (if needed)
            # Note: Playwright MCP might handle viewport differently
            # For now, we just capture it but don't restore it

            logger.info(f"Restored state for session {snapshot.session_id}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to restore state for session {snapshot.session_id}: {e}"
            )
            return False
