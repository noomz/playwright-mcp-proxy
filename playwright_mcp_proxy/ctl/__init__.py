"""CLI management tool entry point for playwright-proxy-ctl."""

from .commands import cli


def main() -> None:
    """Entry point for the playwright-proxy-ctl CLI."""
    cli()
