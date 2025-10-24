"""
Test the exact scenario the user reported.
"""

import asyncio
import json

import httpx


async def main():
    """Test the user's exact scenario."""
    base_url = "http://localhost:34501"

    async with httpx.AsyncClient(timeout=30.0) as client:
        print("Testing user's exact scenario\n")

        # First, let's test if there's an existing session
        # The user might be using an old session_id
        print("1. Testing with a fake session_id (should fail with 404)...")
        proxy_request = {
            "session_id": "fake-session-id-12345",
            "tool": "browser_navigate",
            "params": {"url": "http://localhost:5170/d/8/term-of-references"},
        }

        try:
            response = await client.post(f"{base_url}/proxy", json=proxy_request)
            print(f"   Status code: {response.status_code}")
            print(f"   Response: {response.text[:500]}\n")
        except Exception as e:
            print(f"   Exception: {e}\n")

        # Create a real session
        print("2. Creating session...")
        response = await client.post(f"{base_url}/sessions")
        session_data = response.json()
        session_id = session_data["session_id"]
        print(f"   Session ID: {session_id}\n")

        # Test browser_navigate with localhost URL
        print("3. Testing browser_navigate to localhost...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_navigate",
            "params": {"url": "http://localhost:5170/d/8/term-of-references"},
        }

        try:
            response = await client.post(f"{base_url}/proxy", json=proxy_request)
            print(f"   Status code: {response.status_code}")

            if response.status_code != 200:
                print(f"   ❌ HTTP {response.status_code}")
                print(f"   Response: {response.text}")
                print(f"   Response length: {len(response.text)} bytes\n")
            else:
                result = response.json()
                print(f"   Status: {result['status']}")
                print(f"   Ref ID: {result['ref_id']}")
                if result['status'] == 'error':
                    print(f"   Error: {result.get('error', 'Unknown')}")
                    print(f"   Error length: {len(result.get('error', ''))} bytes")
                print()
        except Exception as e:
            print(f"   Exception: {e}\n")

        # Test browser_click with ref e29
        print("4. Testing browser_click with ref e29...")
        proxy_request = {
            "session_id": session_id,
            "tool": "browser_click",
            "params": {
                "element": "TOR link in navigation",
                "ref": "e29"
            },
        }

        try:
            response = await client.post(f"{base_url}/proxy", json=proxy_request)
            print(f"   Status code: {response.status_code}")

            if response.status_code != 200:
                print(f"   ❌ HTTP {response.status_code}")
                print(f"   Response: {response.text[:1000]}")
                print(f"   Response length: {len(response.text)} bytes\n")
            else:
                result = response.json()
                print(f"   Status: {result['status']}")
                print(f"   Ref ID: {result['ref_id']}")
                if result['status'] == 'error':
                    error = result.get('error', 'Unknown')
                    print(f"   Error: {error}")
                    print(f"   Error length: {len(error)} bytes")
                print()
        except Exception as e:
            print(f"   Exception: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
