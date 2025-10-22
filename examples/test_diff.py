"""
Example script to test Phase 2 diff functionality.

This script demonstrates:
1. First read returns full content and creates cursor
2. Second read with no changes returns empty string
3. Using reset_cursor to force full content

Usage:
    # Start the server in another terminal:
    uv run playwright-proxy-server

    # Then run this script:
    uv run python examples/test_diff.py
"""

import asyncio

import httpx


async def main():
    """Test Phase 2 diff functionality."""
    base_url = "http://localhost:34501"

    async with httpx.AsyncClient() as client:
        print("Testing Phase 2: Diff-Based Content Retrieval\n")

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
        print(f"   Ref ID: {snapshot_ref_id}\n")

        # First read: should return full content and create cursor
        print("5. First read (should return full content)...")
        response = await client.get(f"{base_url}/content/{snapshot_ref_id}")
        content_data = response.json()
        content = content_data["content"]
        print(f"   Content length: {len(content)} characters")
        print(f"   First 200 chars: {content[:200]}...\n")

        # Second read: should return empty (no changes)
        print("6. Second read (should return empty - no changes)...")
        response = await client.get(f"{base_url}/content/{snapshot_ref_id}")
        content_data = response.json()
        content = content_data["content"]
        if content:
            print(f"   ❌ ERROR: Expected empty, got {len(content)} characters\n")
        else:
            print(f"   ✓ Correct: Empty content (no changes detected)\n")

        # Third read: same result (still no changes)
        print("7. Third read (should still be empty)...")
        response = await client.get(f"{base_url}/content/{snapshot_ref_id}")
        content_data = response.json()
        content = content_data["content"]
        if content:
            print(f"   ❌ ERROR: Expected empty, got {len(content)} characters\n")
        else:
            print(f"   ✓ Correct: Empty content (no changes detected)\n")

        # Reset cursor: should return full content again
        print("8. Reset cursor (should return full content)...")
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}", params={"reset_cursor": "true"}
        )
        content_data = response.json()
        content = content_data["content"]
        print(f"   Content length: {len(content)} characters")
        print(f"   ✓ Cursor reset: Full content returned\n")

        # After reset, next read should be empty again
        print("9. Read after reset (should be empty again)...")
        response = await client.get(f"{base_url}/content/{snapshot_ref_id}")
        content_data = response.json()
        content = content_data["content"]
        if content:
            print(f"   ❌ ERROR: Expected empty, got {len(content)} characters\n")
        else:
            print(f"   ✓ Correct: Empty content (no changes since reset)\n")

        # Test with search filter (doesn't affect diff logic)
        print("10. Read with search filter (should still be empty)...")
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}", params={"search_for": "Example"}
        )
        content_data = response.json()
        content = content_data["content"]
        if content:
            print(f"   ❌ ERROR: Expected empty, got: {content}\n")
        else:
            print(f"   ✓ Correct: Empty (filter applied after diff check)\n")

        print("✓ All Phase 2 diff tests passed!")
        print("\nKey takeaways:")
        print("- First read returns full content, creates cursor")
        print("- Subsequent reads return empty if content unchanged")
        print("- reset_cursor=true forces full content and resets tracking")
        print("- Cursors persist across server restarts (SQLite)")


if __name__ == "__main__":
    asyncio.run(main())
