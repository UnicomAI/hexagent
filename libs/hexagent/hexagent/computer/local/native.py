"""Native local computer using transient bash subprocess.

Each command spawns a new process. No state persists between commands.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import sys
import time
from pathlib import Path

from hexagent.computer.base import (
    BASH_MAX_TIMEOUT_MS,
    AsyncComputerMixin,
    Computer,
    ExecutionMetadata,
)
from hexagent.exceptions import CLIError, UnsupportedPlatformError
from hexagent.types import CLIResult


class LocalNativeComputer(AsyncComputerMixin):
    """Local computer using transient bash - each command is a new process."""

    def __init__(self) -> None:
        """Initialize and verify platform compatibility."""
        if sys.platform == "win32":
            msg = "Requires Unix-like system"
            raise UnsupportedPlatformError(msg)

    @property
    def is_running(self) -> bool:
        """Return True; local machine is always available."""
        return True

    async def start(self) -> None:
        """No-op for protocol compliance."""

    async def stop(self) -> None:
        """No-op for protocol compliance."""

    async def upload(self, src: str, dst: str) -> None:
        """Copy a host file into the computer (same filesystem)."""
        self._copy_file(src, dst)

    async def download(self, src: str, dst: str) -> None:
        """Copy a file from the computer to the host (same filesystem)."""
        self._copy_file(src, dst)

    @staticmethod
    def _copy_file(src: str, dst: str) -> None:
        """Copy a single file, creating parent directories as needed."""
        src_path = Path(src)
        if not src_path.exists():
            msg = f"Source file not found: {src}"
            raise FileNotFoundError(msg)
        if not src_path.is_file():
            msg = f"Source is not a file: {src}"
            raise CLIError(msg)

        Path(dst).parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(src, dst)
        except OSError as e:
            msg = f"Failed to copy {src} to {dst}: {e}"
            raise CLIError(msg) from e

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
        input: str | None = None,
    ) -> CLIResult:
        """Execute a command in a new subprocess.

        Args:
            command: Shell command to execute.
            timeout: Command timeout in milliseconds. ``None`` means no timeout
                (block until the process exits or the task is cancelled).
                When specified, capped at ``BASH_MAX_TIMEOUT_MS``.
            input: Optional stdin to pass to the command.
        """
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        start_time = time.monotonic()

        process = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )

        try:
            if timeout is None:
                stdout_bytes, stderr_bytes = await process.communicate(input=input.encode() if input is not None else None)
            else:
                effective_timeout = min(timeout, BASH_MAX_TIMEOUT_MS) / 1000
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(input=input.encode() if input is not None else None),
                    timeout=effective_timeout,
                )
        except TimeoutError:
            await self._kill_process_group(process)
            msg = f"timed out after {effective_timeout}s"
            raise CLIError(msg) from None
        except asyncio.CancelledError:
            await self._kill_process_group(process)
            raise

        stdout = stdout_bytes.decode("utf-8", errors="replace").removesuffix("\n")
        stderr = stderr_bytes.decode("utf-8", errors="replace").removesuffix("\n")

        return CLIResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode or 0,
            metadata=ExecutionMetadata(duration_ms=int((time.monotonic() - start_time) * 1000)),
        )

    @staticmethod
    async def _kill_process_group(process: asyncio.subprocess.Process) -> None:
        """Kill the process group with SIGTERM, then SIGKILL if needed."""
        pid = process.pid
        with contextlib.suppress(OSError):
            os.killpg(pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except TimeoutError:
            with contextlib.suppress(OSError):
                os.killpg(pid, signal.SIGKILL)
            await process.wait()


_: type[Computer] = LocalNativeComputer
