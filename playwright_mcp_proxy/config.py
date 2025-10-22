"""Configuration for Playwright MCP Proxy."""

import os
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings."""

    # Server configuration
    server_host: str = Field(default="localhost", description="HTTP server host")
    server_port: int = Field(default=34501, description="HTTP server port")

    # Database configuration
    database_path: Path = Field(
        default=Path("./proxy.db"),
        description="Path to SQLite database",
    )

    # Playwright configuration
    playwright_command: str = Field(
        default="npx",
        description="Command to run Playwright MCP",
    )
    playwright_args: list[str] = Field(
        default=["@playwright/mcp@latest"],
        description="Arguments for Playwright MCP",
    )
    playwright_browser: Optional[str] = Field(
        default=None,
        description="Browser to use (chrome, firefox, webkit)",
    )
    playwright_headless: bool = Field(
        default=False,
        description="Run browser in headless mode",
    )

    # Subprocess management
    health_check_interval: int = Field(
        default=30,
        description="Health check interval in seconds",
    )
    max_restart_attempts: int = Field(
        default=3,
        description="Max subprocess restart attempts",
    )
    restart_window: int = Field(
        default=300,
        description="Time window for restart attempts (seconds)",
    )
    shutdown_timeout: int = Field(
        default=5,
        description="Graceful shutdown timeout (seconds)",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    class Config:
        """Pydantic config."""

        env_prefix = "PLAYWRIGHT_PROXY_"
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()
