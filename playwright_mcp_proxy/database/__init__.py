"""Database layer for Playwright MCP Proxy."""

from .operations import Database
from .schema import init_database

__all__ = ["init_database", "Database"]
