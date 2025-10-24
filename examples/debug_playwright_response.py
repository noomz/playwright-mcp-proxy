"""
Debug script to see what Playwright actually returns for browser_click.
"""

import asyncio
import json

import httpx


async def main():
    """Test what Playwright returns."""
    base_url = "http://localhost:34501"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Debugging Playwright responses\n")

        # Create session
        response = await client.post(f"{base_url}/sessions")
        session_id = response.json()["session_id"]
        print(f"Session ID: {session_id}\n")

        # Navigate
        print("1. Navigating to example.com...")
        response = await client.post(
            f"{base_url}/proxy",
            json={
                "session_id": session_id,
                "tool": "browser_navigate",
                "params": {"url": "https://example.com"},
            },
        )
        data = response.json()
        ref_id = data["ref_id"]
        print(f"   Response size: {len(response.text)} bytes")
        print(f"   Response: {json.dumps(data, indent=2)}\n")

        # Snapshot
        print("2. Taking snapshot...")
        response = await client.post(
            f"{base_url}/proxy",
            json={"session_id": session_id, "tool": "browser_snapshot", "params": {}},
        )
        data = response.json()
        snapshot_ref_id = data["ref_id"]
        print(f"   Response size: {len(response.text)} bytes")
        print(f"   Response: {json.dumps(data, indent=2)}\n")

        # Get actual snapshot content to see size
        response = await client.get(f"{base_url}/content/{snapshot_ref_id}")
        content = response.json()["content"]
        print(f"   Snapshot content size: {len(content)} bytes")
        print(f"   First 200 chars: {content[:200]}...\n")

        # Click
        print("3. Clicking on link...")
        response = await client.post(
            f"{base_url}/proxy",
            json={
                "session_id": session_id,
                "tool": "browser_click",
                "params": {"element": "More information link", "ref": "e3"},
            },
        )
        data = response.json()
        click_ref_id = data["ref_id"]
        print(f"   Response size: {len(response.text)} bytes")
        print(f"   Response: {json.dumps(data, indent=2)}\n")

        # Check if click stored any content
        response = await client.get(f"{base_url}/content/{click_ref_id}")
        content = response.json()["content"]
        if content:
            print(f"   ⚠️  Click stored content! Size: {len(content)} bytes")
            print(f"   First 200 chars: {content[:200]}...\n")
        else:
            print(f"   ✓ Click stored no content\n")


if __name__ == "__main__":
    asyncio.run(main())
