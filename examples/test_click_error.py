"""
Test script to reproduce browser_click error.

This script simulates the exact scenario that caused the error:
1. Create session
2. Navigate to a page
3. Take snapshot
4. Click on an element
"""

import asyncio
import json

import httpx


async def main():
    """Test browser_click error scenario."""
    base_url = "http://localhost:34501"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Testing browser_click error scenario\n")

        # Create session
        print("1. Creating session...")
        response = await client.post(f"{base_url}/sessions")
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"   Session ID: {session_id}\n")

        # Navigate to a page
        print("2. Navigating to example.com...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_navigate",
            "params": {"url": "https://example.com"},
        }

        try:
            response = await client.post(f"{base_url}/proxy", json=proxy_request)
            print(f"   Status code: {response.status_code}")

            if response.status_code != 200:
                print(f"   ❌ HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return

            result = response.json()
            print(f"   Navigation status: {result['status']}")
            print(f"   Ref ID: {result['ref_id']}\n")

        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return

        # Take snapshot
        print("3. Taking snapshot...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_snapshot",
            "params": {},
        }

        try:
            response = await client.post(f"{base_url}/proxy", json=proxy_request)
            print(f"   Status code: {response.status_code}")

            if response.status_code != 200:
                print(f"   ❌ HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                return

            result = response.json()
            print(f"   Snapshot status: {result['status']}")
            print(f"   Ref ID: {result['ref_id']}")
            print(f"   Response size: {len(str(result))} bytes")
            print(f"   Has snapshot: {result['metadata']['has_snapshot']}\n")

        except Exception as e:
            print(f"   ❌ Exception: {e}")
            return

        # Try to click (simulating with a link element)
        print("4. Attempting browser_click...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_click",
            "params": {
                "element": "More information link",
                "ref": "e3"  # This should exist on example.com
            },
        }

        try:
            response = await client.post(f"{base_url}/proxy", json=proxy_request)
            print(f"   Status code: {response.status_code}")

            if response.status_code != 200:
                print(f"   ❌ HTTP {response.status_code}")
                print(f"   Response body: {response.text[:500]}")

                # Try to parse as JSON to see error details
                try:
                    error_data = response.json()
                    print(f"   Error data: {json.dumps(error_data, indent=2)}")
                except:
                    pass
                return

            result = response.json()
            print(f"   Click status: {result['status']}")
            print(f"   Ref ID: {result['ref_id']}")
            print(f"   Response size: {len(str(result))} bytes")

            if result['status'] == 'error':
                print(f"   Error: {result.get('error', 'Unknown')}")
            else:
                print(f"   ✓ Click succeeded!\n")

        except Exception as e:
            print(f"   ❌ Exception: {e}")
            import traceback
            traceback.print_exc()
            return

        print("\n✓ Test completed")


if __name__ == "__main__":
    asyncio.run(main())
