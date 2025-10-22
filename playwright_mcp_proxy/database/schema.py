"""Database schema initialization."""

import aiosqlite


# SQLite schema DDL
SCHEMA = """
-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    last_activity TIMESTAMP NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active', 'closed', 'error')),
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_state ON sessions(state);
CREATE INDEX IF NOT EXISTS idx_sessions_last_activity ON sessions(last_activity);

-- Requests table
CREATE TABLE IF NOT EXISTS requests (
    ref_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    params TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_requests_session ON requests(session_id);
CREATE INDEX IF NOT EXISTS idx_requests_timestamp ON requests(timestamp);
CREATE INDEX IF NOT EXISTS idx_requests_tool ON requests(tool_name);

-- Responses table
CREATE TABLE IF NOT EXISTS responses (
    ref_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK(status IN ('success', 'error')),
    result TEXT,
    page_snapshot TEXT,
    console_logs TEXT,
    error_message TEXT,
    timestamp TIMESTAMP NOT NULL,
    FOREIGN KEY (ref_id) REFERENCES requests(ref_id)
);

CREATE INDEX IF NOT EXISTS idx_responses_status ON responses(status);
CREATE INDEX IF NOT EXISTS idx_responses_timestamp ON responses(timestamp);

-- Console logs table (normalized)
CREATE TABLE IF NOT EXISTS console_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ref_id TEXT NOT NULL,
    level TEXT NOT NULL CHECK(level IN ('debug', 'info', 'warn', 'error')),
    message TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    location TEXT,
    FOREIGN KEY (ref_id) REFERENCES responses(ref_id)
);

CREATE INDEX IF NOT EXISTS idx_console_logs_ref ON console_logs(ref_id);
CREATE INDEX IF NOT EXISTS idx_console_logs_level ON console_logs(level);
CREATE INDEX IF NOT EXISTS idx_console_logs_timestamp ON console_logs(timestamp);

-- Diff cursors table (Phase 2 - future)
CREATE TABLE IF NOT EXISTS diff_cursors (
    ref_id TEXT PRIMARY KEY,
    cursor_position INTEGER NOT NULL,
    last_snapshot_hash TEXT,
    last_read TIMESTAMP NOT NULL,
    FOREIGN KEY (ref_id) REFERENCES responses(ref_id)
);
"""


async def init_database(db_path: str) -> None:
    """
    Initialize the database with the schema.

    Args:
        db_path: Path to the SQLite database file
    """
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA)
        await db.commit()
