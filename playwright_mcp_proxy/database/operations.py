"""Database operations."""

import json
from datetime import datetime
from typing import Optional

import aiosqlite

from ..models.database import ConsoleLog, DiffCursor, Request, Response, Session


class Database:
    """Database operations wrapper."""

    def __init__(self, db_path: str):
        """
        Initialize database wrapper.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open database connection."""
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

    async def close(self) -> None:
        """Close database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    @property
    def conn(self) -> aiosqlite.Connection:
        """Get database connection."""
        if not self._connection:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    # Session operations

    async def create_session(self, session: Session) -> None:
        """Create a new session."""
        await self.conn.execute(
            """
            INSERT INTO sessions (
                session_id, created_at, last_activity, state, metadata,
                current_url, cookies, local_storage, session_storage, viewport, last_snapshot_time
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session.session_id,
                session.created_at.isoformat(),
                session.last_activity.isoformat(),
                session.state,
                session.metadata,
                session.current_url,
                session.cookies,
                session.local_storage,
                session.session_storage,
                session.viewport,
                session.last_snapshot_time.isoformat() if session.last_snapshot_time else None,
            ),
        )
        await self.conn.commit()

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID."""
        async with self.conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Session(
                session_id=row["session_id"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_activity=datetime.fromisoformat(row["last_activity"]),
                state=row["state"],
                metadata=row["metadata"],
                current_url=row["current_url"],
                cookies=row["cookies"],
                local_storage=row["local_storage"],
                session_storage=row["session_storage"],
                viewport=row["viewport"],
                last_snapshot_time=datetime.fromisoformat(row["last_snapshot_time"]) if row["last_snapshot_time"] else None,
            )

    async def update_session_activity(self, session_id: str) -> None:
        """Update session last activity timestamp."""
        await self.conn.execute(
            "UPDATE sessions SET last_activity = ? WHERE session_id = ?",
            (datetime.now().isoformat(), session_id),
        )
        await self.conn.commit()

    async def update_session_state(self, session_id: str, state: str) -> None:
        """Update session state."""
        await self.conn.execute(
            "UPDATE sessions SET state = ?, last_activity = ? WHERE session_id = ?",
            (state, datetime.now().isoformat(), session_id),
        )
        await self.conn.commit()

    async def list_sessions(self, state: Optional[str] = None) -> list[Session]:
        """List all sessions, optionally filtered by state."""
        query = "SELECT * FROM sessions"
        params = ()
        if state:
            query += " WHERE state = ?"
            params = (state,)
        query += " ORDER BY last_activity DESC"

        sessions = []
        async with self.conn.execute(query, params) as cursor:
            async for row in cursor:
                sessions.append(
                    Session(
                        session_id=row["session_id"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        last_activity=datetime.fromisoformat(row["last_activity"]),
                        state=row["state"],
                        metadata=row["metadata"],
                        current_url=row["current_url"],
                        cookies=row["cookies"],
                        local_storage=row["local_storage"],
                        session_storage=row["session_storage"],
                        viewport=row["viewport"],
                        last_snapshot_time=datetime.fromisoformat(row["last_snapshot_time"]) if row["last_snapshot_time"] else None,
                    )
                )
        return sessions

    # Request operations

    async def create_request(self, request: Request) -> None:
        """Create a new request."""
        await self.conn.execute(
            """
            INSERT INTO requests (ref_id, session_id, tool_name, params, timestamp)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                request.ref_id,
                request.session_id,
                request.tool_name,
                request.params,
                request.timestamp.isoformat(),
            ),
        )
        await self.conn.commit()

    async def get_request(self, ref_id: str) -> Optional[Request]:
        """Get request by ref_id."""
        async with self.conn.execute(
            "SELECT * FROM requests WHERE ref_id = ?", (ref_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Request(
                ref_id=row["ref_id"],
                session_id=row["session_id"],
                tool_name=row["tool_name"],
                params=row["params"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )

    # Response operations

    async def create_response(self, response: Response) -> None:
        """Create a new response."""
        await self.conn.execute(
            """
            INSERT INTO responses
            (ref_id, status, result, page_snapshot, console_logs, error_message, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                response.ref_id,
                response.status,
                response.result,
                response.page_snapshot,
                response.console_logs,
                response.error_message,
                response.timestamp.isoformat(),
            ),
        )
        await self.conn.commit()

    async def get_response(self, ref_id: str) -> Optional[Response]:
        """Get response by ref_id."""
        async with self.conn.execute(
            "SELECT * FROM responses WHERE ref_id = ?", (ref_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return Response(
                ref_id=row["ref_id"],
                status=row["status"],
                result=row["result"],
                page_snapshot=row["page_snapshot"],
                console_logs=row["console_logs"],
                error_message=row["error_message"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )

    # Console log operations

    async def create_console_log(self, log: ConsoleLog) -> None:
        """Create a console log entry."""
        await self.conn.execute(
            """
            INSERT INTO console_logs (ref_id, level, message, timestamp, location)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                log.ref_id,
                log.level,
                log.message,
                log.timestamp.isoformat(),
                log.location,
            ),
        )
        await self.conn.commit()

    async def create_console_logs_batch(self, logs: list[ConsoleLog]) -> None:
        """Create multiple console log entries in a batch."""
        if not logs:
            return

        await self.conn.executemany(
            """
            INSERT INTO console_logs (ref_id, level, message, timestamp, location)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (log.ref_id, log.level, log.message, log.timestamp.isoformat(), log.location)
                for log in logs
            ],
        )
        await self.conn.commit()

    async def get_console_logs(
        self, ref_id: str, level: Optional[str] = None
    ) -> list[ConsoleLog]:
        """Get console logs for a ref_id, optionally filtered by level."""
        query = "SELECT * FROM console_logs WHERE ref_id = ?"
        params: tuple = (ref_id,)

        if level:
            query += " AND level = ?"
            params = (ref_id, level)

        query += " ORDER BY timestamp ASC"

        logs = []
        async with self.conn.execute(query, params) as cursor:
            async for row in cursor:
                logs.append(
                    ConsoleLog(
                        id=row["id"],
                        ref_id=row["ref_id"],
                        level=row["level"],
                        message=row["message"],
                        timestamp=datetime.fromisoformat(row["timestamp"]),
                        location=row["location"],
                    )
                )
        return logs

    async def get_console_error_count(self, ref_id: str) -> int:
        """Get count of console errors for a ref_id."""
        async with self.conn.execute(
            "SELECT COUNT(*) as count FROM console_logs WHERE ref_id = ? AND level = 'error'",
            (ref_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return row["count"] if row else 0

    # Diff cursor operations (Phase 2)

    async def get_diff_cursor(self, ref_id: str) -> Optional[DiffCursor]:
        """Get diff cursor for a ref_id."""
        async with self.conn.execute(
            "SELECT * FROM diff_cursors WHERE ref_id = ?", (ref_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return DiffCursor(
                ref_id=row["ref_id"],
                cursor_position=row["cursor_position"],
                last_snapshot_hash=row["last_snapshot_hash"],
                last_read=datetime.fromisoformat(row["last_read"]),
            )

    async def upsert_diff_cursor(self, cursor: DiffCursor) -> None:
        """Create or update a diff cursor."""
        await self.conn.execute(
            """
            INSERT INTO diff_cursors (ref_id, cursor_position, last_snapshot_hash, last_read)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ref_id) DO UPDATE SET
                cursor_position = excluded.cursor_position,
                last_snapshot_hash = excluded.last_snapshot_hash,
                last_read = excluded.last_read
            """,
            (
                cursor.ref_id,
                cursor.cursor_position,
                cursor.last_snapshot_hash,
                cursor.last_read.isoformat(),
            ),
        )
        await self.conn.commit()

    async def delete_diff_cursor(self, ref_id: str) -> None:
        """Delete a diff cursor (reset)."""
        await self.conn.execute("DELETE FROM diff_cursors WHERE ref_id = ?", (ref_id,))
        await self.conn.commit()
