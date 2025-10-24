"""Database models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Session(BaseModel):
    """Session database model."""

    session_id: str = Field(..., description="Session UUID")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    last_activity: datetime = Field(
        default_factory=datetime.now, description="Last activity timestamp"
    )
    state: str = Field(
        default="active",
        description="Session state: active, closed, error, recoverable, stale, failed"
    )
    metadata: Optional[str] = Field(None, description="Additional metadata as JSON string")

    # Phase 7: Session recovery fields
    current_url: Optional[str] = Field(None, description="Current page URL")
    cookies: Optional[str] = Field(None, description="Cookies as JSON array string")
    local_storage: Optional[str] = Field(None, description="localStorage as JSON object string")
    session_storage: Optional[str] = Field(None, description="sessionStorage as JSON object string")
    viewport: Optional[str] = Field(None, description="Viewport as JSON object {width, height}")
    last_snapshot_time: Optional[datetime] = Field(None, description="Last state snapshot time")


class Request(BaseModel):
    """Request database model."""

    ref_id: str = Field(..., description="Request UUID")
    session_id: str = Field(..., description="Session UUID")
    tool_name: str = Field(..., description="Tool name")
    params: str = Field(..., description="Tool parameters as JSON string")
    timestamp: datetime = Field(default_factory=datetime.now, description="Request timestamp")


class Response(BaseModel):
    """Response database model."""

    ref_id: str = Field(..., description="Request UUID (FK to requests)")
    status: str = Field(..., description="Response status: success or error")
    result: Optional[str] = Field(None, description="Full response as JSON string blob")
    page_snapshot: Optional[str] = Field(None, description="Page snapshot as TEXT blob")
    console_logs: Optional[str] = Field(
        None, description="Console logs as JSON string (backup)"
    )
    error_message: Optional[str] = Field(None, description="Error message if failed")
    timestamp: datetime = Field(default_factory=datetime.now, description="Response timestamp")


class ConsoleLog(BaseModel):
    """Console log database model."""

    id: Optional[int] = Field(None, description="Auto-increment ID")
    ref_id: str = Field(..., description="Request UUID (FK to responses)")
    level: str = Field(..., description="Log level: debug, info, warn, error")
    message: str = Field(..., description="Log message")
    timestamp: datetime = Field(default_factory=datetime.now, description="Log timestamp")
    location: Optional[str] = Field(
        None, description="Log location as JSON: {url, lineNumber, columnNumber}"
    )


class DiffCursor(BaseModel):
    """Diff cursor database model (Phase 2)."""

    ref_id: str = Field(..., description="Request UUID (FK to responses)")
    cursor_position: int = Field(default=0, description="Byte offset for text comparison")
    last_snapshot_hash: Optional[str] = Field(
        None, description="Hash of last returned content"
    )
    last_read: datetime = Field(default_factory=datetime.now, description="Last read timestamp")


class SessionSnapshot(BaseModel):
    """Session snapshot database model (Phase 7: Session recovery)."""

    id: Optional[int] = Field(None, description="Auto-increment ID")
    session_id: str = Field(..., description="Session UUID (FK to sessions)")
    current_url: Optional[str] = Field(None, description="Current page URL")
    cookies: Optional[str] = Field(None, description="Cookies as JSON array string")
    local_storage: Optional[str] = Field(None, description="localStorage as JSON object string")
    session_storage: Optional[str] = Field(None, description="sessionStorage as JSON object string")
    viewport: Optional[str] = Field(None, description="Viewport as JSON object {width, height}")
    snapshot_time: datetime = Field(default_factory=datetime.now, description="Snapshot timestamp")
