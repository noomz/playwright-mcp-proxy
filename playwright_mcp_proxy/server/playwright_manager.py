"""Playwright MCP subprocess manager."""

import asyncio
import json
import logging
import time
import traceback
from asyncio.subprocess import Process
from collections import deque
from typing import Any, Optional

from ..config import settings

logger = logging.getLogger(__name__)


class PlaywrightManager:
    """Manages the Playwright MCP subprocess lifecycle."""

    def __init__(self):
        """Initialize the Playwright manager."""
        self.process: Optional[Process] = None
        self.is_healthy = False
        self.restart_attempts: deque[float] = deque(maxlen=settings.max_restart_attempts)
        self._health_check_task: Optional[asyncio.Task] = None
        self._message_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the Playwright MCP subprocess."""
        logger.info("Starting Playwright MCP subprocess...")

        # Build command
        command = [settings.playwright_command] + settings.playwright_args

        # Add browser flag if specified
        if settings.playwright_browser:
            command.extend(["--browser", settings.playwright_browser])

        # Add headless flag if specified
        if settings.playwright_headless:
            command.append("--headless")

        # Spawn subprocess
        try:
            self.process = await asyncio.create_subprocess_exec(
                *command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            logger.info(f"Playwright subprocess started with PID {self.process.pid}")

            # Send MCP initialize handshake
            await self._send_initialize()

            # Mark as healthy
            self.is_healthy = True

            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            # Start stderr monitor
            asyncio.create_task(self._monitor_stderr())

        except Exception as e:
            logger.error(f"Failed to start Playwright subprocess: {e}")
            raise

    async def stop(self) -> None:
        """Stop the Playwright MCP subprocess gracefully."""
        logger.info("Stopping Playwright MCP subprocess...")

        # Cancel health check
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Terminate process
        if self.process:
            try:
                # Try graceful shutdown
                self.process.terminate()
                try:
                    await asyncio.wait_for(
                        self.process.wait(), timeout=settings.shutdown_timeout
                    )
                except asyncio.TimeoutError:
                    # Force kill if timeout
                    logger.warning("Graceful shutdown timeout, sending SIGKILL")
                    self.process.kill()
                    await self.process.wait()

                logger.info("Playwright subprocess stopped")
            except Exception as e:
                logger.error(f"Error stopping subprocess: {e}")

        self.is_healthy = False
        self.process = None

    async def _read_line_chunked(self, stream: asyncio.StreamReader) -> bytes:
        """
        Read a line from stream, handling lines that exceed buffer limit.

        This handles asyncio.LimitOverrunError that occurs when a single line
        exceeds the default 64KB buffer limit. Solution based on:
        https://github.com/ipython/ipython/issues/14005

        Args:
            stream: The asyncio StreamReader to read from

        Returns:
            Complete line as bytes
        """
        chunks = []

        while True:
            try:
                # Try to read until newline
                chunk = await stream.readuntil(b'\n')
                chunks.append(chunk)
                break  # Successfully found newline
            except asyncio.IncompleteReadError as e:
                # EOF reached before newline
                chunks.append(e.partial)
                break
            except asyncio.LimitOverrunError as e:
                # Line exceeds buffer limit - read what's available and continue
                chunk = await stream.read(e.consumed)
                chunks.append(chunk)
                # Continue loop to read more until we find newline

        return b''.join(chunks)

    async def send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """
        Send a JSON-RPC request to Playwright MCP.

        Args:
            method: MCP method name (e.g., 'tools/call')
            params: Method parameters

        Returns:
            Response from Playwright MCP

        Raises:
            RuntimeError: If subprocess is not healthy
        """
        if not self.is_healthy or not self.process or not self.process.stdin:
            raise RuntimeError("Playwright subprocess is not healthy")

        async with self._lock:
            self._message_id += 1
            message = {
                "jsonrpc": "2.0",
                "id": self._message_id,
                "method": method,
                "params": params,
            }

            # Send request
            request_line = json.dumps(message) + "\n"
            self.process.stdin.write(request_line.encode())
            await self.process.stdin.drain()

            # Read response
            if not self.process.stdout:
                raise RuntimeError("Subprocess stdout is not available")

            # Use chunked reading to handle large responses (>64KB)
            response_line = await self._read_line_chunked(self.process.stdout)
            if not response_line:
                raise RuntimeError("Subprocess returned empty response")

            response = json.loads(response_line.decode())

            # Check for error
            if "error" in response:
                raise RuntimeError(f"Playwright MCP error: {response['error']}")

            return response.get("result", {})

    async def _send_initialize(self) -> None:
        """Send MCP initialize handshake."""
        try:
            # Note: This is a simplified handshake
            # Real MCP protocol may require more complex initialization
            result = await self.send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "playwright-proxy", "version": "0.1.0"},
                },
            )
            logger.info(f"MCP initialized: {result}")
        except Exception as e:
            logger.warning(f"MCP initialize failed (may be optional): {e}")

    async def _health_check_loop(self) -> None:
        """Background task to monitor subprocess health."""
        consecutive_failures = 0

        while True:
            try:
                await asyncio.sleep(settings.health_check_interval)

                # Check if process is alive
                if self.process and self.process.returncode is not None:
                    logger.error(
                        f"Playwright subprocess died with code {self.process.returncode}"
                    )
                    self.is_healthy = False
                    await self._attempt_restart()
                    consecutive_failures = 0
                    continue

                # Try a simple ping (tools/list is a safe read-only operation)
                try:
                    await asyncio.wait_for(
                        self.send_request("tools/list", {}), timeout=5.0
                    )
                    consecutive_failures = 0
                except Exception as e:
                    consecutive_failures += 1
                    logger.warning(
                        f"Health check failed ({consecutive_failures}/3): {e}"
                    )

                    if consecutive_failures >= 3:
                        logger.error("Health check failed 3 times, marking unhealthy")
                        self.is_healthy = False
                        await self._attempt_restart()
                        consecutive_failures = 0

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

    async def _attempt_restart(self) -> None:
        """Attempt to restart the subprocess with exponential backoff."""
        now = time.time()

        # Clean up old restart attempts outside the window
        while (
            self.restart_attempts
            and now - self.restart_attempts[0] > settings.restart_window
        ):
            self.restart_attempts.popleft()

        # Check if we've exceeded max attempts
        if len(self.restart_attempts) >= settings.max_restart_attempts:
            logger.error(
                f"Max restart attempts ({settings.max_restart_attempts}) "
                f"exceeded in {settings.restart_window}s window"
            )
            return

        # Record this attempt
        self.restart_attempts.append(now)

        # Calculate backoff (1s, 2s, 4s, ...)
        backoff = 2 ** (len(self.restart_attempts) - 1)
        logger.info(f"Restarting subprocess in {backoff}s...")
        await asyncio.sleep(backoff)

        # Stop existing process
        await self.stop()

        # Start new process
        try:
            await self.start()
            logger.info("Subprocess restarted successfully")
        except Exception as e:
            logger.error(f"Failed to restart subprocess: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")

    async def _monitor_stderr(self) -> None:
        """Monitor subprocess stderr for logging."""
        if not self.process or not self.process.stderr:
            return

        try:
            while True:
                line = await self.process.stderr.readline()
                if not line:
                    break
                logger.debug(f"Playwright stderr: {line.decode().strip()}")
        except Exception as e:
            logger.error(f"Error monitoring stderr: {e}")
