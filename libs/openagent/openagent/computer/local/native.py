"""Native local computer using transient bash subprocess.

Each command spawns a new process. No state persists between commands.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

from openagent.computer.base import (
    BASH_DEFAULT_TIMEOUT_MS,
    BASH_MAX_TIMEOUT_MS,
    AsyncComputerMixin,
    Computer,
    ExecutionMetadata,
)
from openagent.exceptions import CLIError, UnsupportedPlatformError
from openagent.types import CLIResult


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

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> CLIResult:
        """Execute a command in a new subprocess."""
        timeout_ms = timeout if timeout is not None else BASH_DEFAULT_TIMEOUT_MS
        timeout_ms = min(timeout_ms, BASH_MAX_TIMEOUT_MS)
        effective_timeout = timeout_ms / 1000
        start_time = time.monotonic()

        env = os.environ.copy()
        env["NO_COLOR"] = "1"

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=effective_timeout,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            msg = f"timed out after {effective_timeout}s"
            raise CLIError(msg) from None

        stdout = stdout_bytes.decode("utf-8", errors="replace").removesuffix("\n")
        stderr = stderr_bytes.decode("utf-8", errors="replace").removesuffix("\n")

        return CLIResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=process.returncode or 0,
            metadata=ExecutionMetadata(duration_ms=int((time.monotonic() - start_time) * 1000)),
        )


_: type[Computer] = LocalNativeComputer
