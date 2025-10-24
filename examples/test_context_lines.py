"""
Test script to demonstrate grep-like context lines feature in get_content.

This script demonstrates:
1. Search without context (basic filter)
2. Search with -A (after lines)
3. Search with -B (before lines)
4. Search with both -A and -B (context lines)

Usage:
    # Start the server in another terminal:
    uv run playwright-proxy-server

    # Then run this script:
    uv run python examples/test_context_lines.py
"""

import asyncio

import httpx


async def main():
    """Test context lines feature."""
    base_url = "http://localhost:34501"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Testing Context Lines Feature (grep-like -A/-B)\n")
        print("=" * 60)

        # Create session
        print("\n1. Creating session...")
        response = await client.post(f"{base_url}/sessions")
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"   Session ID: {session_id}")

        # Navigate to a page
        print("\n2. Navigating to example.com...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_navigate",
            "params": {"url": "https://example.com"},
        }
        response = await client.post(f"{base_url}/proxy", json=proxy_request)
        result = response.json()
        print(f"   Status: {result['status']}")

        # Take snapshot
        print("\n3. Taking snapshot...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_snapshot",
            "params": {},
        }
        response = await client.post(f"{base_url}/proxy", json=proxy_request)
        result = response.json()
        snapshot_ref_id = result["ref_id"]
        print(f"   Ref ID: {snapshot_ref_id}")

        # Test 1: Basic search without context
        print("\n" + "=" * 60)
        print("TEST 1: Search for 'Example' without context")
        print("=" * 60)
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}",
            params={"search_for": "Example"}
        )
        content = response.json()["content"]
        print(content)

        # Test 2: Search with after_lines (like grep -A 2)
        print("\n" + "=" * 60)
        print("TEST 2: Search for 'Example' with 2 lines after (like grep -A 2)")
        print("=" * 60)
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}",
            params={"search_for": "Example", "after_lines": 2}
        )
        content = response.json()["content"]
        print(content)

        # Test 3: Search with before_lines (like grep -B 1)
        print("\n" + "=" * 60)
        print("TEST 3: Search for 'domain' with 1 line before (like grep -B 1)")
        print("=" * 60)
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}",
            params={"search_for": "domain", "before_lines": 1}
        )
        content = response.json()["content"]
        print(content)

        # Test 4: Search with both before and after (like grep -C 2)
        print("\n" + "=" * 60)
        print("TEST 4: Search for 'information' with 2 lines before and after")
        print("=" * 60)
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}",
            params={"search_for": "information", "before_lines": 2, "after_lines": 2}
        )
        content = response.json()["content"]
        print(content)

        # Test 5: Show gap separator
        print("\n" + "=" * 60)
        print("TEST 5: Multiple matches showing gap separator ('--')")
        print("=" * 60)
        response = await client.get(
            f"{base_url}/content/{snapshot_ref_id}",
            params={"search_for": "ref=", "after_lines": 1}
        )
        content = response.json()["content"]
        print(content)

        print("\n" + "=" * 60)
        print("✓ All context line tests completed!")
        print("\nKey Features:")
        print("- before_lines: Include N lines before each match (like grep -B)")
        print("- after_lines: Include N lines after each match (like grep -A)")
        print("- Combines both for full context (like grep -C)")
        print("- Shows '--' separator between non-contiguous matches")
        print("- Works with diff cursors and reset_cursor parameter")


if __name__ == "__main__":
    asyncio.run(main())
