"""Tests for BUGF-01, BUGF-02, BUGF-03 bug fixes."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from playwright_mcp_proxy.database import Database, init_database
from playwright_mcp_proxy.models.database import ConsoleLog, Request, Response, Session
from playwright_mcp_proxy.server.app import _filter_console_blob_by_level, _parse_console_blob

# Sample console log blob used across multiple tests
SAMPLE_BLOB = """Total messages: 4 (Errors: 2, Warnings: 1)
Returning 4 messages for level "debug"

[ERROR] Uncaught TypeError: Cannot read property 'foo' of null @ https://example.com:42
[WARNING] Deprecated API usage @ https://example.com:10
[LOG] Page loaded @ https://example.com:1
[DEBUG] Verbose trace info @ https://example.com:99
"""


@pytest.fixture
async def db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    await init_database(db_path)

    database = Database(db_path)
    await database.connect()

    yield database

    await database.close()
    Path(db_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# BUGF-01: Params serialization
# ---------------------------------------------------------------------------


def test_request_params_valid_json():
    """json.dumps produces valid JSON that json.loads can round-trip."""
    params = {"url": "https://example.com"}
    serialized = json.dumps(params)
    # Must be valid JSON
    deserialized = json.loads(serialized)
    assert deserialized == params


def test_request_params_str_is_invalid_json():
    """str() produces single-quoted Python repr which json.loads rejects (regression guard)."""
    params = {"url": "https://example.com"}
    python_repr = str(params)
    with pytest.raises(json.JSONDecodeError):
        json.loads(python_repr)


# ---------------------------------------------------------------------------
# BUGF-02 + BUGF-03: Console blob parser
# ---------------------------------------------------------------------------


def test_parse_console_blob_extracts_entries():
    """_parse_console_blob returns structured entries with normalized levels."""
    entries = _parse_console_blob(SAMPLE_BLOB)
    # Should produce 4 entries (one per [PREFIX] line)
    assert len(entries) == 4

    levels = [e["level"] for e in entries]
    assert "error" in levels    # [ERROR]
    assert "warn" in levels     # [WARNING] normalized to 'warn'
    assert "info" in levels     # [LOG] normalized to 'info'
    assert "debug" in levels    # [DEBUG]


def test_parse_console_blob_skips_headers():
    """_parse_console_blob skips 'Total messages:' and 'Returning ' header lines."""
    entries = _parse_console_blob(SAMPLE_BLOB)
    texts = [e["text"] for e in entries]
    # No header lines should appear
    for text in texts:
        assert not text.startswith("Total messages:")
        assert not text.startswith("Returning ")


def test_filter_console_blob_error_only():
    """_filter_console_blob_by_level(blob, 'error') returns only [ERROR] lines."""
    result = _filter_console_blob_by_level(SAMPLE_BLOB, "error")
    lines = [l for l in result.split("\n") if l.strip()]
    assert len(lines) == 1
    assert lines[0].startswith("[ERROR]")


def test_filter_console_blob_info_includes_higher():
    """_filter_console_blob_by_level(blob, 'info') returns error + warning + info but not debug."""
    result = _filter_console_blob_by_level(SAMPLE_BLOB, "info")
    lines = [l for l in result.split("\n") if l.strip()]
    # Should include error, warning, info but NOT debug
    line_prefixes = [l.split("]")[0] + "]" for l in lines if l.startswith("[")]
    assert "[ERROR]" in line_prefixes
    assert "[WARNING]" in line_prefixes
    assert "[LOG]" in line_prefixes
    assert "[DEBUG]" not in line_prefixes


def test_filter_console_blob_no_level():
    """_filter_console_blob_by_level(blob, 'debug') returns all lines (most permissive)."""
    result = _filter_console_blob_by_level(SAMPLE_BLOB, "debug")
    lines = [l for l in result.split("\n") if l.strip()]
    assert len(lines) == 4


# ---------------------------------------------------------------------------
# BUGF-02: console_error_count wired to DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_console_error_count_from_parsed_blob(db):
    """
    After parsing a blob with 2 error lines and inserting via create_console_logs_batch,
    get_console_error_count returns 2.
    """
    # Create FK prerequisites
    session = Session(
        session_id="bugf-session-1",
        created_at=datetime.now(),
        last_activity=datetime.now(),
        state="active",
    )
    await db.create_session(session)

    request = Request(
        ref_id="bugf-ref-1",
        session_id="bugf-session-1",
        tool_name="browser_console_messages",
        params="{}",
        timestamp=datetime.now(),
    )
    await db.create_request(request)

    response = Response(
        ref_id="bugf-ref-1",
        status="success",
        timestamp=datetime.now(),
    )
    await db.create_response(response)

    # Blob with 2 errors
    blob_with_two_errors = """[ERROR] First error @ https://example.com:1
[ERROR] Second error @ https://example.com:2
[WARNING] Just a warning @ https://example.com:3
[LOG] Info message @ https://example.com:4
"""
    entries = _parse_console_blob(blob_with_two_errors)

    logs = [
        ConsoleLog(
            ref_id="bugf-ref-1",
            level=entry["level"],
            message=entry["text"],
            timestamp=datetime.now(),
        )
        for entry in entries
    ]
    await db.create_console_logs_batch(logs)

    error_count = await db.get_console_error_count("bugf-ref-1")
    assert error_count == 2
