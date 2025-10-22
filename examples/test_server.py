"""
Example script to test the HTTP server directly.

This script demonstrates:
1. Starting a session
2. Making a proxied request
3. Retrieving content

Usage:
    # Start the server in another terminal:
    uv run playwright-proxy-server

    # Then run this script:
    uv run python examples/test_server.py
"""

import asyncio

import httpx


async def main():
    """Test the HTTP server."""
    base_url = "http://localhost:34501"

    async with httpx.AsyncClient() as client:
        print("Testing Playwright MCP Proxy HTTP Server\n")

        # Check health
        print("1. Checking server health...")
        response = await client.get(f"{base_url}/health")
        print(f"   Status: {response.json()}\n")

        # Create session
        print("2. Creating new session...")
        response = await client.post(f"{base_url}/sessions")
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"   Session ID: {session_id}\n")

        # Navigate to a URL
        print("3. Navigating to example.com...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_navigate",
            "params": {"url": "https://example.com"},
        }
        response = await client.post(f"{base_url}/proxy", json=proxy_request)
        result = response.json()
        print(f"   Status: {result['status']}")
        print(f"   Ref ID: {result['ref_id']}\n")

        # Take a snapshot
        print("4. Taking page snapshot...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_snapshot",
            "params": {},
        }
        response = await client.post(f"{base_url}/proxy", json=proxy_request)
        result = response.json()
        snapshot_ref_id = result["ref_id"]
        print(f"   Status: {result['status']}")
        print(f"   Ref ID: {snapshot_ref_id}")
        print(f"   Metadata: {result['metadata']}\n")

        # Get content
        print("5. Retrieving snapshot content...")
        response = await client.get(f"{base_url}/content/{snapshot_ref_id}")
        content_data = response.json()
        content = content_data["content"]
        print(f"   Content length: {len(content)} characters")
        print(f"   First 200 chars:\n   {content[:200]}...\n")

        # Search content
        print("6. Searching for 'Example Domain'...")
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}", params={"search_for": "Example Domain"}
        )
        content_data = response.json()
        filtered = content_data["content"]
        print(f"   Filtered content:\n   {filtered}\n")

        print("✓ All tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
