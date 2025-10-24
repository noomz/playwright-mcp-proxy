"""FastAPI server application."""

import asyncio
import hashlib
import json
import logging
import sys
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings
from ..database import Database, init_database
from ..models.api import ErrorResponse, ProxyRequest, ProxyResponse, ResponseMetadata
from ..models.database import DiffCursor, Request, Response, Session
from .playwright_manager import PlaywrightManager
from .session_state import SessionStateManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Global state
playwright_manager: PlaywrightManager
database: Database
session_state_manager: SessionStateManager
snapshot_task: Optional[asyncio.Task] = None


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


def truncate_error(error_msg: str, max_length: int = 500) -> str:
    """Truncate error message to prevent MCP protocol size limits."""
    if len(error_msg) <= max_length:
        return error_msg
    return error_msg[:max_length] + f"... (truncated, {len(error_msg)} total chars)"


async def periodic_snapshot_task():
    """
    Background task that periodically captures session state for active sessions.

    Phase 7: This task runs every session_snapshot_interval seconds and:
    1. Finds all active sessions
    2. Captures their current browser state
    3. Saves snapshots to database
    4. Cleans up old snapshots (keeps last N)
    """
    logger.info(
        f"Starting periodic snapshot task (interval: {settings.session_snapshot_interval}s)"
    )

    while True:
        try:
            await asyncio.sleep(settings.session_snapshot_interval)

            # Get all active sessions
            active_sessions = await database.list_sessions(state="active")

            if not active_sessions:
                logger.debug("No active sessions to snapshot")
                continue

            logger.debug(f"Capturing state for {len(active_sessions)} active sessions")

            for session in active_sessions:
                try:
                    # Capture current state
                    snapshot = await session_state_manager.capture_state(
                        session.session_id
                    )

                    if snapshot:
                        # Save snapshot to database
                        await database.save_session_snapshot(snapshot)

                        # Update session's inline state fields
                        await database.update_session_state_from_snapshot(
                            session.session_id, snapshot
                        )

                        # Cleanup old snapshots (keep last N)
                        await database.cleanup_old_snapshots(
                            session.session_id, keep_last=settings.max_session_snapshots
                        )

                        logger.debug(f"Snapshot saved for session {session.session_id}")
                    else:
                        logger.warning(
                            f"Failed to capture state for session {session.session_id}"
                        )

                except Exception as e:
                    logger.error(
                        f"Error capturing state for session {session.session_id}: {e}"
                    )
                    # Continue with other sessions even if one fails

        except asyncio.CancelledError:
            logger.info("Periodic snapshot task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic snapshot task: {e}")
            # Continue running even if there's an error


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global playwright_manager, database, session_state_manager, snapshot_task

    # Startup
    logger.info("Starting Playwright MCP Proxy server...")

    # Initialize database
    await init_database(str(settings.database_path))
    database = Database(str(settings.database_path))
    await database.connect()
    logger.info(f"Database initialized at {settings.database_path}")

    # Start Playwright manager
    playwright_manager = PlaywrightManager()
    await playwright_manager.start()
    logger.info("Playwright subprocess started")

    # Initialize session state manager (Phase 7)
    session_state_manager = SessionStateManager(playwright_manager)
    logger.info("Session state manager initialized")

    # Start periodic snapshot task (Phase 7)
    snapshot_task = asyncio.create_task(periodic_snapshot_task())
    logger.info("Periodic snapshot task started")

    yield

    # Shutdown
    logger.info("Shutting down Playwright MCP Proxy server...")

    # Stop periodic snapshot task
    if snapshot_task:
        snapshot_task.cancel()
        try:
            await snapshot_task
        except asyncio.CancelledError:
            pass
        logger.info("Periodic snapshot task stopped")

    # Stop Playwright manager
    await playwright_manager.stop()

    # Close database
    await database.close()

    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Playwright MCP Proxy",
        description="HTTP proxy for Playwright MCP with persistent storage",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy" if playwright_manager.is_healthy else "degraded",
            "playwright_subprocess": "running" if playwright_manager.is_healthy else "down",
        }

    @app.post("/sessions", response_model=dict[str, str])
    async def create_session():
        """Create a new browser session."""
        session_id = str(uuid.uuid4())

        # Create session in database
        session = Session(
            session_id=session_id,
            created_at=datetime.now(),
            last_activity=datetime.now(),
            state="active",
        )
        await database.create_session(session)

        logger.info(f"Created session {session_id}")
        return {"session_id": session_id}

    @app.post("/proxy", response_model=ProxyResponse)
    async def proxy_request(request: ProxyRequest):
        """
        Proxy a request to Playwright MCP and persist the response.

        Args:
            request: Proxy request with session_id, tool, and params

        Returns:
            ProxyResponse with ref_id and metadata
        """
        # Verify session exists and is active
        session = await database.get_session(request.session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        if session.state != "active":
            raise HTTPException(status_code=400, detail=f"Session is {session.state}")

        # Generate ref_id
        ref_id = request.request_id or str(uuid.uuid4())

        # Create request record
        db_request = Request(
            ref_id=ref_id,
            session_id=request.session_id,
            tool_name=request.tool,
            params=str(request.params),  # Store as JSON string
            timestamp=datetime.now(),
        )
        await database.create_request(db_request)

        # Update session activity
        await database.update_session_activity(request.session_id)

        try:
            # Send request to Playwright MCP
            result = await playwright_manager.send_request(
                "tools/call",
                {"name": request.tool, "arguments": request.params},
            )

            # Extract page snapshot if available
            page_snapshot = None
            console_logs_data = None

            # Check if this was a browser_snapshot call
            if request.tool == "browser_snapshot" and "content" in result:
                page_snapshot = result["content"][0].get("text", "")

            # Check if this was a browser_console_messages call
            if request.tool == "browser_console_messages" and "content" in result:
                console_logs_data = result["content"][0].get("text", "")

            # Store response
            # Only store essential metadata from result, not the full payload
            # to avoid database bloat and serialization issues
            result_metadata = {
                "tool": request.tool,
                "isError": result.get("isError", False),
            }

            db_response = Response(
                ref_id=ref_id,
                status="success",
                result=json.dumps(result_metadata),  # Store minimal metadata, not full response
                page_snapshot=page_snapshot,
                console_logs=console_logs_data,
                timestamp=datetime.now(),
            )
            await database.create_response(db_response)

            # Build metadata
            metadata = ResponseMetadata(
                tool=request.tool,
                has_snapshot=page_snapshot is not None,
                has_console_logs=console_logs_data is not None,
                console_error_count=0,  # TODO: Parse and count errors
            )

            return ProxyResponse(
                ref_id=ref_id,
                session_id=request.session_id,
                status="success",
                timestamp=datetime.now(),
                metadata=metadata,
            )

        except Exception as e:
            error_str = str(e)
            logger.error(f"Error proxying request: {error_str[:500]}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")

            # Truncate error message for storage and MCP response
            truncated_error = truncate_error(error_str, max_length=500)

            # Store error response
            db_response = Response(
                ref_id=ref_id,
                status="error",
                error_message=error_str,  # Store full error in DB
                timestamp=datetime.now(),
            )
            await database.create_response(db_response)

            # Update session state to error
            await database.update_session_state(request.session_id, "error")

            return ProxyResponse(
                ref_id=ref_id,
                session_id=request.session_id,
                status="error",
                timestamp=datetime.now(),
                metadata=ResponseMetadata(tool=request.tool),
                error=truncated_error,  # Return truncated error to prevent MCP size limits
            )

    @app.get("/content/{ref_id}")
    async def get_content(
        ref_id: str,
        search_for: str = "",
        reset_cursor: bool = False,
        before_lines: int = 0,
        after_lines: int = 0,
    ):
        """
        Get page snapshot content for a ref_id with diff support (Phase 2).

        Args:
            ref_id: Reference ID
            search_for: Optional substring to filter by
            reset_cursor: If True, reset diff cursor and return full content
            before_lines: Number of context lines before match (like grep -B)
            after_lines: Number of context lines after match (like grep -A)

        Returns:
            Page snapshot content (diff or full based on cursor state)
        """
        response = await database.get_response(ref_id)
        if not response:
            raise HTTPException(status_code=404, detail="Response not found")

        if not response.page_snapshot:
            return {"content": ""}

        content = response.page_snapshot

        # Apply search filter with context lines if provided (before diff logic)
        if search_for:
            all_lines = content.split("\n")
            matching_indices = set()

            # Find all matching line indices
            for i, line in enumerate(all_lines):
                if search_for in line:
                    # Add the matching line
                    matching_indices.add(i)
                    # Add context lines before
                    for b in range(1, before_lines + 1):
                        if i - b >= 0:
                            matching_indices.add(i - b)
                    # Add context lines after
                    for a in range(1, after_lines + 1):
                        if i + a < len(all_lines):
                            matching_indices.add(i + a)

            # Extract lines in order, adding separator for gaps
            if matching_indices:
                result_lines = []
                sorted_indices = sorted(matching_indices)
                prev_idx = None

                for idx in sorted_indices:
                    # Add separator if there's a gap
                    if prev_idx is not None and idx - prev_idx > 1:
                        result_lines.append("--")
                    result_lines.append(all_lines[idx])
                    prev_idx = idx

                content = "\n".join(result_lines)
            else:
                content = ""

        # Phase 2: Diff logic
        if reset_cursor:
            # Reset cursor and return full content
            await database.delete_diff_cursor(ref_id)
            # Create new cursor with current content hash
            content_hash = compute_hash(content)
            cursor = DiffCursor(
                ref_id=ref_id,
                cursor_position=len(content),
                last_snapshot_hash=content_hash,
                last_read=datetime.now(),
            )
            await database.upsert_diff_cursor(cursor)
            return {"content": content}

        # Check for existing cursor
        cursor = await database.get_diff_cursor(ref_id)

        if not cursor:
            # First read: return full content and create cursor
            content_hash = compute_hash(content)
            cursor = DiffCursor(
                ref_id=ref_id,
                cursor_position=len(content),
                last_snapshot_hash=content_hash,
                last_read=datetime.now(),
            )
            await database.upsert_diff_cursor(cursor)
            return {"content": content}

        # Cursor exists: check if content changed
        content_hash = compute_hash(content)

        if cursor.last_snapshot_hash == content_hash:
            # Content unchanged: return empty string
            # Update last_read timestamp
            cursor.last_read = datetime.now()
            await database.upsert_diff_cursor(cursor)
            return {"content": ""}

        # Content changed: return full new content (simple diff strategy)
        # Update cursor with new hash
        cursor.cursor_position = len(content)
        cursor.last_snapshot_hash = content_hash
        cursor.last_read = datetime.now()
        await database.upsert_diff_cursor(cursor)
        return {"content": content}

    @app.get("/console/{ref_id}")
    async def get_console_content(ref_id: str, level: str = ""):
        """
        Get console logs for a ref_id.

        Args:
            ref_id: Reference ID
            level: Optional level filter (debug, info, warn, error)

        Returns:
            Console logs
        """
        response = await database.get_response(ref_id)
        if not response:
            raise HTTPException(status_code=404, detail="Response not found")

        # Check normalized console_logs table first
        logs = await database.get_console_logs(ref_id, level if level else None)
        if logs:
            # Format logs
            formatted = []
            for log in logs:
                formatted.append(
                    f"[{log.level.upper()}] {log.timestamp.isoformat()}: {log.message}"
                )
            return {"content": "\n".join(formatted)}

        # Fallback to stored console_logs blob
        if response.console_logs:
            content = response.console_logs
            # TODO: Parse JSON and filter by level if needed
            return {"content": content}

        return {"content": ""}

    return app


def main():
    """Main entry point for the server."""
    import uvicorn

    uvicorn.run(
        "playwright_mcp_proxy.server.app:create_app",
        host=settings.server_host,
        port=settings.server_port,
        factory=True,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
