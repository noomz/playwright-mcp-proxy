"""MCP client server - exposes Playwright tools via MCP stdio protocol."""

import asyncio
import logging
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from ..config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# HTTP client for communicating with the proxy server
http_client: httpx.AsyncClient
current_session_id: str | None = None


# Define tools
TOOLS = [
    Tool(
        name="create_new_session",
        description="Create a new Playwright browser session",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_content",
        description="Get page snapshot content from a previous request (Phase 2: with diff support)",
        inputSchema={
            "type": "object",
            "properties": {
                "ref_id": {
                    "type": "string",
                    "description": "Reference ID from a previous request",
                },
                "search_for": {
                    "type": "string",
                    "description": "Optional substring to filter content",
                },
                "reset_cursor": {
                    "type": "boolean",
                    "description": "Reset diff cursor and return full content (default: false)",
                },
            },
            "required": ["ref_id"],
        },
    ),
    Tool(
        name="get_console_content",
        description="Get console logs from a previous request",
        inputSchema={
            "type": "object",
            "properties": {
                "ref_id": {
                    "type": "string",
                    "description": "Reference ID from a previous request",
                },
                "level": {
                    "type": "string",
                    "description": "Log level filter: debug, info, warn, error",
                    "enum": ["", "debug", "info", "warn", "error"],
                },
            },
            "required": ["ref_id"],
        },
    ),
    # Playwright tools (proxied)
    Tool(
        name="browser_navigate",
        description="Navigate to a URL",
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to navigate to"},
            },
            "required": ["url"],
        },
    ),
    Tool(
        name="browser_snapshot",
        description="Capture accessibility snapshot of the current page",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="browser_click",
        description="Click on an element",
        inputSchema={
            "type": "object",
            "properties": {
                "element": {"type": "string", "description": "Element description"},
                "ref": {"type": "string", "description": "Element reference from snapshot"},
            },
            "required": ["element", "ref"],
        },
    ),
    Tool(
        name="browser_type",
        description="Type text into an element",
        inputSchema={
            "type": "object",
            "properties": {
                "element": {"type": "string", "description": "Element description"},
                "ref": {"type": "string", "description": "Element reference from snapshot"},
                "text": {"type": "string", "description": "Text to type"},
                "submit": {"type": "boolean", "description": "Press Enter after typing"},
            },
            "required": ["element", "ref", "text"],
        },
    ),
    Tool(
        name="browser_console_messages",
        description="Get console messages from the browser",
        inputSchema={
            "type": "object",
            "properties": {
                "onlyErrors": {
                    "type": "boolean",
                    "description": "Only return error messages",
                },
            },
        },
    ),
    Tool(
        name="browser_close",
        description="Close the browser",
        inputSchema={"type": "object", "properties": {}},
    ),
]


async def handle_tool_call(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """
    Handle a tool call by routing to the appropriate handler.

    Args:
        name: Tool name
        arguments: Tool arguments

    Returns:
        List of text content responses
    """
    global current_session_id

    server_url = f"http://{settings.server_host}:{settings.server_port}"

    try:
        # Handle session creation
        if name == "create_new_session":
            response = await http_client.post(f"{server_url}/sessions")
            response.raise_for_status()
            data = response.json()
            current_session_id = data["session_id"]
            return [TextContent(type="text", text=f"Created session: {current_session_id}")]

        # Handle content retrieval
        if name == "get_content":
            ref_id = arguments["ref_id"]
            search_for = arguments.get("search_for", "")
            reset_cursor = arguments.get("reset_cursor", False)
            params = {}
            if search_for:
                params["search_for"] = search_for
            if reset_cursor:
                params["reset_cursor"] = "true"
            response = await http_client.get(f"{server_url}/content/{ref_id}", params=params)
            response.raise_for_status()
            data = response.json()
            content = data["content"]

            # Add helpful message if content is empty due to no changes
            if not content and not reset_cursor:
                return [TextContent(
                    type="text",
                    text="(No changes since last read. Use reset_cursor=true to get full content.)"
                )]

            return [TextContent(type="text", text=content)]

        # Handle console content retrieval
        if name == "get_console_content":
            ref_id = arguments["ref_id"]
            level = arguments.get("level", "")
            params = {"level": level} if level else {}
            response = await http_client.get(f"{server_url}/console/{ref_id}", params=params)
            response.raise_for_status()
            data = response.json()
            return [TextContent(type="text", text=data["content"])]

        # Handle proxied Playwright tools
        if not current_session_id:
            return [
                TextContent(
                    type="text",
                    text="Error: No active session. Call create_new_session first.",
                )
            ]

        # Proxy request to server
        proxy_request = {
            "session_id": current_session_id,
            "tool": name,
            "params": arguments,
        }

        response = await http_client.post(f"{server_url}/proxy", json=proxy_request)
        response.raise_for_status()
        data = response.json()

        # Format response with metadata only (Phase 1 policy)
        # Keep responses very short to avoid MCP protocol buffer limits
        if data["status"] == "success":
            metadata = data["metadata"]
            result_text = f"✓ {metadata['tool']} | {data['ref_id']}"

            if metadata.get("has_snapshot"):
                result_text += f" | snapshot: get_content('{data['ref_id']}')"

            if metadata.get("has_console_logs"):
                result_text += f" | logs: get_console_content('{data['ref_id']}')"

            return [TextContent(type="text", text=result_text)]
        else:
            # Truncate error to prevent buffer overflow
            error_msg = str(data.get('error', 'Unknown error'))[:200]
            return [
                TextContent(
                    type="text",
                    text=f"✗ {data['ref_id']} | {error_msg}",
                )
            ]

    except httpx.HTTPError as e:
        logger.error(f"HTTP error calling tool {name}: {e}")
        # Truncate to avoid MCP buffer limits
        error_str = str(e)[:200]
        return [TextContent(type="text", text=f"HTTP error: {error_str}")]
    except Exception as e:
        logger.error(f"Error calling tool {name}: {e}")
        # Truncate to avoid MCP buffer limits
        error_str = str(e)[:200]
        return [TextContent(type="text", text=f"Error: {error_str}")]


async def run_mcp_server():
    """Run the MCP server."""
    global http_client

    # Create HTTP client
    http_client = httpx.AsyncClient(timeout=30.0)

    # Create MCP server
    server = Server("playwright-mcp-proxy-client")

    # Register list_tools handler
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    # Register call_tool handler
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        return await handle_tool_call(name, arguments)

    # Run server
    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP client server started")
            await server.run(read_stream, write_stream, server.create_initialization_options())
    finally:
        await http_client.aclose()


def main():
    """Main entry point for the MCP client."""
    asyncio.run(run_mcp_server())


if __name__ == "__main__":
    main()
