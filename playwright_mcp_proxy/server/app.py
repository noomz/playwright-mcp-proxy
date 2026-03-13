"""FastAPI server application."""

import asyncio
import hashlib
import json
import logging
import traceback
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException

from ..config import settings
from ..database import Database, init_database
from ..models.api import ProxyRequest, ProxyResponse, ResponseMetadata
from ..models.database import ConsoleLog, DiffCursor, Request, Response, Session
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


async def detect_orphaned_sessions():
    """
    Phase 7.2: Detect and classify orphaned sessions on startup.

    Called during server startup to find sessions that were active when the
    server last stopped and classify them based on snapshot age:
    - recoverable: Recent snapshot (< max_session_age), can be restored
    - stale: Old snapshot (> max_session_age), may not work reliably
    - closed: No snapshot or very old, cannot be recovered

    This allows users to resume sessions after a server restart.
    """
    logger.info("Detecting orphaned sessions from previous server instance...")

    try:
        # Find all sessions still marked as "active"
        # These are sessions that were running when the server stopped
        active_sessions = await database.list_sessions(state="active")

        if not active_sessions:
            logger.info("No orphaned sessions found")
            return

        logger.info(f"Found {len(active_sessions)} potentially orphaned sessions")

        recoverable_count = 0
        stale_count = 0
        closed_count = 0

        for session in active_sessions:
            try:
                logger.debug(f"Processing session {session.session_id}")

                # Get the latest snapshot for this session
                logger.debug(f"Getting latest snapshot for session {session.session_id}")
                snapshot = await database.get_latest_session_snapshot(session.session_id)
                logger.debug(f"Got snapshot for session {session.session_id}: {snapshot is not None}")

                if not snapshot:
                    # No snapshot exists - cannot recover
                    logger.info(
                        f"Session {session.session_id}: No snapshot, marking as closed"
                    )
                    await database.update_session_state(session.session_id, "closed")
                    closed_count += 1
                    continue

                # Calculate age of snapshot
                logger.debug(f"Accessing snapshot_time for session {session.session_id}")
                age_seconds = (datetime.now() - snapshot.snapshot_time).total_seconds()
                logger.debug(f"Calculated age for session {session.session_id}: {age_seconds}s")

                if age_seconds <= settings.max_session_age:
                    # Recent snapshot - recoverable
                    logger.info(
                        f"Session {session.session_id}: Recent snapshot "
                        f"({int(age_seconds)}s old), marking as recoverable"
                    )
                    await database.update_session_state(session.session_id, "recoverable")
                    recoverable_count += 1
                else:
                    # Old snapshot - stale
                    logger.info(
                        f"Session {session.session_id}: Stale snapshot "
                        f"({int(age_seconds)}s old), marking as stale"
                    )
                    await database.update_session_state(session.session_id, "stale")
                    stale_count += 1

            except (KeyError, IndexError) as e:
                logger.error(
                    f"Error processing session {session.session_id} - {type(e).__name__} with key/index: {e}. "
                    f"Marking as failed"
                )
                await database.update_session_state(session.session_id, "failed")
            except Exception as e:
                logger.error(
                    f"Error processing session {session.session_id}: {type(e).__name__}: {e}. "
                    f"Marking as failed"
                )
                await database.update_session_state(session.session_id, "failed")

        logger.info(
            f"Session detection complete: {recoverable_count} recoverable, "
            f"{stale_count} stale, {closed_count} closed"
        )

    except (KeyError, IndexError) as e:
        logger.error(f"Error detecting orphaned sessions - {type(e).__name__} with key/index: {e}")
    except Exception as e:
        logger.error(f"Error detecting orphaned sessions: {type(e).__name__}: {e}")


async def periodic_snapshot_task():
    """
    Background task that periodically captures session state for active sessions.

    Phase 7: This task runs every session_snapshot_interval seconds and:
    1. Finds all active sessions
    2. Captures their current browser state
    3. Saves snapshots to database
    4. Cleans up old snapshots (keeps last N)
    5. Marks sessions as closed after 3 consecutive capture failures (tab closed)
    """
    logger.info(
        f"Starting periodic snapshot task (interval: {settings.session_snapshot_interval}s)"
    )

    # Track consecutive capture failures per session
    capture_failures: dict[str, int] = {}
    max_failures = 3

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
                        # Reset failure counter on success
                        capture_failures.pop(session.session_id, None)

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
                        # Track consecutive failures — tab likely closed
                        failures = capture_failures.get(session.session_id, 0) + 1
                        capture_failures[session.session_id] = failures

                        if failures >= max_failures:
                            logger.info(
                                f"Marking session {session.session_id} as closed "
                                f"after {failures} consecutive capture failures (tab closed)"
                            )
                            await database.update_session_state(
                                session.session_id, "closed"
                            )
                            capture_failures.pop(session.session_id, None)
                        else:
                            logger.debug(
                                f"Capture failed for session {session.session_id} "
                                f"({failures}/{max_failures} before auto-close)"
                            )

                except (KeyError, IndexError) as e:
                    logger.error(
                        f"Error capturing state for session {session.session_id} - {type(e).__name__} with key/index: {e}"
                    )
                    # Continue with other sessions even if one fails
                except Exception as e:
                    logger.error(
                        f"Error capturing state for session {session.session_id}: {type(e).__name__}: {e}"
                    )
                    # Continue with other sessions even if one fails

        except asyncio.CancelledError:
            logger.info("Periodic snapshot task cancelled")
            break
        except (KeyError, IndexError) as e:
            logger.error(f"Error in periodic snapshot task - {type(e).__name__} with key/index: {e}")
            # Continue running even if there's an error
        except Exception as e:
            logger.error(f"Error in periodic snapshot task: {type(e).__name__}: {e}")
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

    # Detect orphaned sessions from previous instance (Phase 7.2)
    await detect_orphaned_sessions()

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


# Console log severity ordering (matches Playwright's consoleMessageLevels)
CONSOLE_LEVEL_ORDER = ["error", "warning", "info", "debug"]


def _get_level_from_prefix(line: str) -> str | None:
    """Extract normalized level from [LEVEL] prefix. Returns schema-compatible level or None."""
    if not line.startswith("["):
        return None
    bracket_end = line.find("]")
    if bracket_end == -1:
        return None
    prefix = line[1:bracket_end].lower()
    if prefix in ("error", "assert"):
        return "error"
    elif prefix == "warning":
        return "warn"  # schema uses 'warn' not 'warning'
    elif prefix in ("debug", "trace", "clear", "endgroup", "profile",
                    "profileend", "startgroup", "startgroupcollapsed"):
        return "debug"
    else:
        return "info"  # log, info, count, dir, dirxml, table, time, timeend, etc.


def _parse_console_blob(blob: str) -> list[dict]:
    """Parse plain-text console log blob into structured entries."""
    entries = []
    for line in blob.split("\n"):
        if not line.strip():
            continue
        level = _get_level_from_prefix(line)
        if level is None:
            continue
        entries.append({"level": level, "text": line})
    return entries


def _filter_console_blob_by_level(blob: str, threshold_level: str) -> str:
    """Filter blob lines by severity threshold (matches Playwright's shouldIncludeMessage)."""
    if not blob:
        return ""
    threshold_idx = CONSOLE_LEVEL_ORDER.index(threshold_level) if threshold_level in CONSOLE_LEVEL_ORDER else 2
    result_lines = []
    for line in blob.split("\n"):
        if not line.strip():
            continue
        level = _get_level_from_prefix(line)
        if level is None:
            continue
        # _get_level_from_prefix returns 'warn' for schema; need 'warning' for CONSOLE_LEVEL_ORDER lookup
        lookup_level = "warning" if level == "warn" else level
        msg_idx = CONSOLE_LEVEL_ORDER.index(lookup_level) if lookup_level in CONSOLE_LEVEL_ORDER else 2
        if msg_idx <= threshold_idx:
            result_lines.append(line)
    return "\n".join(result_lines)


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

    @app.get("/sessions")
    async def list_sessions(state: Optional[str] = None):
        """
        List all sessions, optionally filtered by state.

        Phase 7.2: Allows users to see recoverable sessions after a restart.

        Args:
            state: Optional state filter (active, closed, error, recoverable, stale, failed)

        Returns:
            List of sessions with metadata
        """
        sessions = await database.list_sessions(state=state)

        # Format sessions for response
        result = []
        for session in sessions:
            session_data = {
                "session_id": session.session_id,
                "state": session.state,
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
                "current_url": session.current_url,
                "has_snapshot": session.last_snapshot_time is not None,
            }

            # Add snapshot age if available
            if session.last_snapshot_time:
                age_seconds = (datetime.now() - session.last_snapshot_time).total_seconds()
                session_data["snapshot_age_seconds"] = int(age_seconds)

            result.append(session_data)

        return {"sessions": result, "count": len(result)}

    @app.post("/sessions/{session_id}/resume")
    async def resume_session(session_id: str):
        """
        Resume a recoverable session by restoring its state.

        Phase 7.3: Allows users to resume sessions after server restart.

        Args:
            session_id: Session ID to resume

        Returns:
            Status of resume operation
        """
        # Get session
        session = await database.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Only allow resuming recoverable or stale sessions
        if session.state not in ["recoverable", "stale"]:
            raise HTTPException(
                status_code=400,
                detail=f"Session is {session.state}, cannot resume. "
                f"Only recoverable or stale sessions can be resumed.",
            )

        try:
            # Get latest snapshot
            snapshot = await database.get_latest_session_snapshot(session_id)
            if not snapshot:
                raise HTTPException(
                    status_code=400,
                    detail="No snapshot available for this session",
                )

            # Restore state
            success = await session_state_manager.restore_state(snapshot)

            if success:
                # Update session state to active
                await database.update_session_state(session_id, "active")
                logger.info(f"Successfully resumed session {session_id}")

                return {
                    "session_id": session_id,
                    "status": "resumed",
                    "restored_url": snapshot.current_url,
                    "snapshot_age_seconds": int(
                        (datetime.now() - snapshot.snapshot_time).total_seconds()
                    ),
                }
            else:
                # Restoration failed
                await database.update_session_state(session_id, "failed")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to restore session state",
                )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error resuming session {session_id}: {e}")
            await database.update_session_state(session_id, "failed")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resume session: {str(e)}",
            )

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
            params=json.dumps(request.params),  # Store as JSON string
            timestamp=datetime.now(),
        )
        await database.create_request(db_request)
        # COMMIT 1 is internal to create_request (audit trail: request is durable before RPC fires)

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
            await database.create_response_no_commit(db_response)

            # Parse console blob and populate normalized table (BUGF-02)
            if console_logs_data:
                entries = _parse_console_blob(console_logs_data)
                if entries:
                    logs = [
                        ConsoleLog(
                            ref_id=ref_id,
                            level=entry["level"],
                            message=entry["text"],
                            timestamp=datetime.now(),
                        )
                        for entry in entries
                    ]
                    await database.create_console_logs_batch_no_commit(logs)

            # Bug fix: update current_url after successful browser_navigate
            if request.tool == "browser_navigate" and "url" in request.params:
                await database.update_session_url_no_commit(
                    request.session_id, request.params["url"]
                )

            # Bug fix: mark session closed and suppress restart after browser_close
            if request.tool == "browser_close":
                await database.update_session_state_no_commit(request.session_id, "closed")
                playwright_manager._intentional_close = True

            # Update session activity (moved from pre-RPC to post-RPC batch)
            await database.update_session_activity_no_commit(request.session_id)

            # COMMIT 2: batch all post-RPC writes in a single commit
            await database.commit()

            # Get actual error count from normalized table (BUGF-02)
            # Runs after commit — same connection sees its own writes
            error_count = await database.get_console_error_count(ref_id)

            # Build metadata
            metadata = ResponseMetadata(
                tool=request.tool,
                has_snapshot=page_snapshot is not None,
                has_console_logs=console_logs_data is not None,
                console_error_count=error_count,
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
            await database.create_response_no_commit(db_response)

            # Only mark session as "error" for infrastructure failures, not
            # tool-level Playwright errors (stale ref, element not found, etc.)
            # Playwright MCP tool errors come back as RuntimeError("Playwright MCP error: ...")
            # which means the subprocess is healthy — the tool just failed.
            is_tool_error = (
                isinstance(e, RuntimeError) and str(e).startswith("Playwright MCP error:")
            )
            if not is_tool_error:
                await database.update_session_state_no_commit(request.session_id, "error")

            # COMMIT 2: batch error response + optional session state update
            await database.commit()

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
            if level:
                content = _filter_console_blob_by_level(response.console_logs, level)
            else:
                content = response.console_logs
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
