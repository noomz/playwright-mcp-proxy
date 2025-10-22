"""API models for HTTP requests and responses."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProxyRequest(BaseModel):
    """Request to the proxy server."""

    session_id: str = Field(..., description="Session UUID")
    tool: str = Field(..., description="Tool name to call")
    params: dict[str, Any] = Field(default_factory=dict, description="Tool parameters")
    request_id: Optional[str] = Field(None, description="Optional request UUID")


class ResponseMetadata(BaseModel):
    """Metadata about the response."""

    tool: str = Field(..., description="Tool that was called")
    has_snapshot: bool = Field(default=False, description="Whether response has page snapshot")
    has_console_logs: bool = Field(
        default=False, description="Whether response has console logs"
    )
    console_error_count: int = Field(default=0, description="Number of console errors")


class ProxyResponse(BaseModel):
    """Response from the proxy server."""

    ref_id: str = Field(..., description="Reference ID for this request")
    session_id: str = Field(..., description="Session UUID")
    status: str = Field(..., description="Status: success or error")
    timestamp: datetime = Field(..., description="Response timestamp")
    metadata: ResponseMetadata = Field(..., description="Response metadata")
    error: Optional[str] = Field(None, description="Error message if status is error")


class ErrorResponse(BaseModel):
    """Error response."""

    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[dict[str, Any]] = Field(None, description="Additional error details")
