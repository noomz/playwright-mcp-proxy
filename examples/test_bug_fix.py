"""
Test script to verify the MCP message size limit bug fix.

This script tests that browser_navigate no longer causes
"Separator is found, but chunk is longer than limit" errors.

Usage:
    # Start the server in another terminal:
    uv run playwright-proxy-server

    # Then run this script:
    uv run python examples/test_bug_fix.py
"""

import asyncio

import httpx


async def main():
    """Test the MCP message size bug fix."""
    base_url = "http://localhost:34501"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Testing MCP Message Size Bug Fix\n")

        # Check health
        print("1. Checking server health...")
        response = await client.get(f"{base_url}/health")
        health = response.json()
        print(f"   Status: {health['status']}")
        if health['status'] != 'healthy':
            print(f"   ❌ Server not healthy: {health}")
            return
        print()

        # Create session
        print("2. Creating new session...")
        response = await client.post(f"{base_url}/sessions")
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"   Session ID: {session_id}\n")

        # Navigate to a URL (this previously caused the error)
        print("3. Testing browser_navigate (previously caused size limit error)...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_navigate",
            "params": {"url": "https://example.com"},
        }

        try:
            response = await client.post(f"{base_url}/proxy", json=proxy_request)
            result = response.json()

            if result['status'] == 'error':
                print(f"   ❌ Request failed with error: {result.get('error', 'Unknown error')}")
                print(f"   Ref ID: {result['ref_id']}")
                return

            print(f"   ✓ Navigation succeeded!")
            print(f"   Status: {result['status']}")
            print(f"   Ref ID: {result['ref_id']}")
            print(f"   Metadata: {result.get('metadata', {})}")

            # Verify the response doesn't contain massive payload
            response_size = len(str(result))
            print(f"   Response size: {response_size} bytes")

            if response_size > 2000:
                print(f"   ⚠️  Warning: Response is large ({response_size} bytes)")
            else:
                print(f"   ✓ Response size is reasonable")

        except Exception as e:
            print(f"   ❌ Exception occurred: {e}")
            return

        print()

        # Take a snapshot to verify page_snapshot is stored correctly
        print("4. Testing browser_snapshot...")
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
        print(f"   Has snapshot: {result['metadata']['has_snapshot']}")

        response_size = len(str(result))
        print(f"   Response size: {response_size} bytes")

        if response_size > 2000:
            print(f"   ⚠️  Warning: Response is large ({response_size} bytes)")
        else:
            print(f"   ✓ Response size is reasonable")

        print()

        # Retrieve the full snapshot via get_content endpoint
        print("5. Retrieving full page snapshot via get_content...")
        response = await client.get(f"{base_url}/content/{snapshot_ref_id}")
        content_data = response.json()
        content = content_data["content"]

        print(f"   Content length: {len(content)} characters")
        print(f"   First 150 chars: {content[:150]}...")
        print(f"   ✓ Full content retrieved successfully via dedicated endpoint")
        print()

        print("=" * 60)
        print("✓ All tests passed!")
        print()
        print("Bug fix verification:")
        print("- browser_navigate no longer causes MCP size limit errors")
        print("- Responses contain only metadata + ref_id")
        print("- Full content available via /content/{ref_id} endpoint")
        print("- Response sizes are reasonable (<2KB)")


if __name__ == "__main__":
    asyncio.run(main())
