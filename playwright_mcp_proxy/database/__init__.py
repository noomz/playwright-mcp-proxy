"""Database layer for Playwright MCP Proxy."""

from .schema import init_database
from .operations import Database

__all__ = ["init_database", "Database"]
