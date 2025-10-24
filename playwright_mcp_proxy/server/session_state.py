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

        Extracts:
        - Current URL
        - Cookies
        - localStorage
        - sessionStorage
        - Viewport size

        Args:
            session_id: Session ID to capture state for

        Returns:
            SessionSnapshot with captured state, or None if capture fails
        """
        try:
            # 1. Get current URL using browser_evaluate
            url_result = await self.playwright.send_request(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {
                        "function": "() => window.location.href",
                    },
                },
            )
            current_url = self._extract_evaluate_result(url_result)

            # 2. Get cookies - Playwright MCP likely exposes this via context
            # For now, we'll use browser_evaluate to get document.cookie
            # In a real implementation, we'd want to use the Playwright context API
            # which gives us full cookie objects with domain, path, httpOnly, etc.
            cookies_result = await self.playwright.send_request(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {
                        "function": "() => document.cookie",
                    },
                },
            )
            cookies_str = self._extract_evaluate_result(cookies_result)

            # Store as JSON array for better structure (convert from cookie string)
            cookies_json = json.dumps(self._parse_cookie_string(cookies_str))

            # 3. Get localStorage
            localstorage_result = await self.playwright.send_request(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {
                        "function": "() => JSON.stringify(localStorage)",
                    },
                },
            )
            local_storage = self._extract_evaluate_result(localstorage_result)

            # 4. Get sessionStorage
            sessionstorage_result = await self.playwright.send_request(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {
                        "function": "() => JSON.stringify(sessionStorage)",
                    },
                },
            )
            session_storage = self._extract_evaluate_result(sessionstorage_result)

            # 5. Get viewport size
            viewport_result = await self.playwright.send_request(
                "tools/call",
                {
                    "name": "browser_evaluate",
                    "arguments": {
                        "function": "() => JSON.stringify({width: window.innerWidth, height: window.innerHeight})",
                    },
                },
            )
            viewport = self._extract_evaluate_result(viewport_result)

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

            # 2. Restore localStorage
            if snapshot.local_storage:
                # Parse JSON and restore each key
                storage_data = json.loads(snapshot.local_storage)
                for key, value in storage_data.items():
                    # Escape quotes in value for JavaScript
                    value_escaped = value.replace("\\", "\\\\").replace("'", "\\'")
                    await self.playwright.send_request(
                        "tools/call",
                        {
                            "name": "browser_evaluate",
                            "arguments": {
                                "function": f"() => localStorage.setItem('{key}', '{value_escaped}')",
                            },
                        },
                    )

            # 3. Restore sessionStorage
            if snapshot.session_storage:
                # Parse JSON and restore each key
                storage_data = json.loads(snapshot.session_storage)
                for key, value in storage_data.items():
                    value_escaped = value.replace("\\", "\\\\").replace("'", "\\'")
                    await self.playwright.send_request(
                        "tools/call",
                        {
                            "name": "browser_evaluate",
                            "arguments": {
                                "function": f"() => sessionStorage.setItem('{key}', '{value_escaped}')",
                            },
                        },
                    )

            # 4. Restore cookies (simplified - just set document.cookie)
            # Note: This is limited - real implementation should use context.addCookies()
            if snapshot.cookies:
                cookies_list = json.loads(snapshot.cookies)
                for cookie in cookies_list:
                    cookie_str = f"{cookie['name']}={cookie['value']}"
                    await self.playwright.send_request(
                        "tools/call",
                        {
                            "name": "browser_evaluate",
                            "arguments": {
                                "function": f"() => document.cookie = '{cookie_str}'",
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
