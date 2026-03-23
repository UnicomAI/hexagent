"""E2B cloud computer with automatic pause/resume support.

Each command runs in an isolated E2B sandbox. State (cwd, env vars, files)
persists within the sandbox session and across pause/resume cycles.

Key features:
- Auto-pause when sandbox approaches timeout (preserves state)
- Auto-resume transparently on next run() call
- Reconnection support via sandbox_id parameter
- Pre-command safety check to prevent mid-command expiration

Pricing (as of Jan 2025):
    Base rates:
        CPU: $0.0504/core/hr
        Memory: $0.0162/GiB/hr

    Available templates:
        openagent-c1-m1  1 CPU, 1 GiB Memory   $0.0666/hr
        openagent-c2-m4  2 CPU, 4 GiB Memory   $0.1656/hr  (alias: "openagent")
        openagent-c4-m8  4 CPU, 8 GiB Memory   $0.3312/hr
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from openagent.computer.base import (
    BASH_MAX_TIMEOUT_MS,
    AsyncComputerMixin,
    Computer,
    ExecutionMetadata,
)
from openagent.exceptions import CLIError, ConfigurationError, MissingDependencyError
from openagent.types import CLIResult

if TYPE_CHECKING:
    from e2b import AsyncSandbox

SANDBOX_DEFAULT_LIFETIME_S = 600  # 10 minutes sandbox lifetime
_SAFETY_BUFFER_S = 60  # Buffer time before sandbox expiry
_E2B_MAX_LIFETIME_S = 3600  # 1 hour hard limit for Hobby users

_logger = logging.getLogger(__name__)


class RemoteE2BComputer(AsyncComputerMixin):
    """Cloud computer running in an E2B sandbox with persistence support.

    Uses E2B's commands.run() API for command execution. State (cwd, env vars,
    files, installed packages) persists within the sandbox session and across
    pause/resume cycles.

    Features:
        - Auto-pause: Sandbox is paused (not killed) when timeout approaches
        - Auto-resume: Paused sandbox resumes transparently on next run()
        - Reconnection: Pass sandbox_id to reconnect to existing sandbox
        - Safety check: Ensures sandbox won't expire mid-command

    Requires E2B_API_KEY environment variable.

    Examples:
        Basic usage (auto-manages lifecycle):
            async with RemoteE2BComputer() as computer:
                result = await computer.run("echo hello")

        Reconnection (across process restarts):
            # First session
            computer1 = RemoteE2BComputer()
            await computer1.start()
            sandbox_id = computer1.sandbox_id  # Save this!
            await computer1.run("pip install pandas")
            await computer1.stop()  # Pauses, preserves state

            # Later session (even after process restart)
            computer2 = RemoteE2BComputer(sandbox_id=sandbox_id)
            await computer2.run("python -c 'import pandas'")  # Works!
    """

    def __init__(
        self,
        template: str | None = None,
        *,
        lifetime: int = SANDBOX_DEFAULT_LIFETIME_S,
        sandbox_id: str | None = None,
    ) -> None:
        """Initialize E2B computer.

        Args:
            template: Sandbox template ID or name. If None, uses E2B's default
                base template. Custom templates can be created using the E2B CLI.
            lifetime: Sandbox lifetime in seconds (default 10 minutes). When
                this timeout is approached, the sandbox is paused automatically.
            sandbox_id: Optional sandbox ID to reconnect to an existing sandbox.
                Use this to resume work after process restart or pause.
        """
        if "E2B_API_KEY" not in os.environ:
            msg = "E2B_API_KEY environment variable not set. Get your API key at https://e2b.dev/docs"
            raise ConfigurationError(msg)
        self._template = template
        self._lifetime = lifetime
        self._sandbox: AsyncSandbox | None = None
        self._sandbox_id: str | None = sandbox_id
        self._is_paused: bool = sandbox_id is not None

    @property
    def sandbox_id(self) -> str | None:
        """Current sandbox ID for persistence/reconnection.

        This ID can be stored externally and passed to a new RemoteE2BComputer
        instance to reconnect to the same sandbox. The sandbox preserves its
        state (files, installed packages, etc.) across reconnections.

        Returns:
            Sandbox ID string, or None if no sandbox has been created.
        """
        if self._sandbox is not None:
            sandbox_id: str = self._sandbox.sandbox_id
            return sandbox_id
        return self._sandbox_id

    @property
    def is_running(self) -> bool:
        """Check if the sandbox is currently running (not paused or stopped)."""
        return self._sandbox is not None and not self._is_paused

    async def start(self) -> None:
        """Start, resume, or reconnect to sandbox.

        Behavior:
            - If sandbox is already running: no-op
            - If sandbox is paused: resumes it
            - If sandbox_id is set: attempts to reconnect/resume
            - Otherwise: creates a new sandbox

        Idempotent - safe to call multiple times.
        """
        if self._sandbox is not None and not self._is_paused:
            return

        try:
            from e2b import AsyncSandbox
        except ImportError as e:
            msg = "E2B package not installed. Install with: pip install e2b"
            raise MissingDependencyError(msg) from e

        # Try reconnection/resume first if we have a sandbox ID (from pause or external)
        if self._sandbox_id is not None:
            try:
                self._sandbox = await AsyncSandbox.connect(
                    self._sandbox_id,
                    timeout=self._lifetime,
                )
                self._is_paused = False
            except Exception as e:  # noqa: BLE001
                # Sandbox gone (expired after 30 days, killed externally, etc.)
                _logger.warning(
                    "Failed to reconnect to sandbox %s: %s. Creating new sandbox.",
                    self._sandbox_id,
                    e,
                )
                self._sandbox_id = None
                self._sandbox = None
                self._is_paused = False
            else:
                _logger.info("Reconnected to sandbox %s", self._sandbox_id)
                return

        # Create fresh sandbox with auto_pause so E2B pauses (not kills)
        # the sandbox when the timeout expires, preserving state for resume.
        try:
            self._sandbox = await AsyncSandbox.beta_create(
                self._template,
                timeout=self._lifetime,
                auto_pause=True,
            )
            self._sandbox_id = self._sandbox.sandbox_id
            self._is_paused = False
            _logger.info("Created new sandbox %s", self._sandbox_id)
        except Exception as e:
            msg = f"Failed to create E2B sandbox: {e}"
            raise CLIError(msg) from e

    async def _pause(self) -> None:
        """Pause the sandbox, preserving all state.

        The sandbox can be resumed by calling start() or run(), or by creating
        a new RemoteE2BComputer instance with the same sandbox_id.

        Paused sandboxes are preserved by E2B for up to 30 days.
        """
        if self._sandbox is None or self._is_paused:
            return

        sandbox_id = self._sandbox.sandbox_id
        try:
            await self._sandbox.beta_pause()
            self._sandbox_id = sandbox_id
            self._sandbox = None  # Release stale SDK object (holds httpx client)
            self._is_paused = True
            _logger.info("Sandbox %s paused (state preserved)", sandbox_id)
        except Exception as e:
            msg = f"Failed to pause sandbox: {e}"
            raise CLIError(msg) from e

    async def stop(self) -> None:
        """Pause the sandbox, preserving state for later resume.

        This is called automatically when exiting async context manager.
        The sandbox can be resumed by calling start() or run() on a new
        RemoteE2BComputer instance with the same sandbox_id.

        Use _kill() to permanently destroy the sandbox.

        Idempotent - safe to call multiple times.
        """
        if self._sandbox is None or self._is_paused:
            return

        try:
            await self._pause()
        except CLIError:
            # Pause failed, fall back to kill
            await self._kill()

    async def _kill(self) -> None:
        """Permanently destroy the sandbox. Cannot be resumed.

        Use this when you want to clean up and not preserve state.
        After calling _kill(), sandbox_id will be None.
        """
        if self._sandbox is not None:
            sandbox_id = self._sandbox.sandbox_id
            with contextlib.suppress(Exception):
                await self._sandbox.kill()
                _logger.info("Sandbox %s killed (permanently destroyed)", sandbox_id)
            self._sandbox = None

        self._sandbox_id = None
        self._is_paused = False

    async def upload(self, src: str, dst: str) -> None:
        """Transfer a file from the host to the E2B sandbox."""
        if self._sandbox is None or self._is_paused:
            await self.start()
        if self._sandbox is None or self._is_paused:
            msg = "Failed to start sandbox"
            raise CLIError(msg)

        src_path = Path(src)
        if not src_path.exists():
            msg = f"Source file not found: {src}"
            raise FileNotFoundError(msg)
        if not src_path.is_file():
            msg = f"Source is not a file: {src}"
            raise CLIError(msg)

        try:
            await self._sandbox.files.write(dst, src_path.read_bytes())
        except (FileNotFoundError, CLIError):
            raise
        except Exception as e:
            msg = f"Failed to upload {src} to sandbox: {e}"
            raise CLIError(msg) from e

    async def download(self, src: str, dst: str) -> None:
        """Transfer a file from the E2B sandbox to the host."""
        if self._sandbox is None or self._is_paused:
            await self.start()
        if self._sandbox is None or self._is_paused:
            msg = "Failed to start sandbox"
            raise CLIError(msg)

        dst_path = Path(dst)
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            data = await self._sandbox.files.read(src, format="bytes")
            dst_path.write_bytes(data)
        except Exception as e:
            msg = f"Failed to download {src} from sandbox: {e}"
            raise CLIError(msg) from e

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> CLIResult:
        """Execute a command in the sandbox.

        Auto-starts if not running. Auto-resumes if paused.
        Ensures sandbox won't expire during command execution.

        Args:
            command: Shell command to execute.
            timeout: Command timeout in milliseconds (default 120000ms).

        Returns:
            CLIResult with stdout, stderr, and exit_code.

        Raises:
            CLIError: If sandbox cannot be started or command fails to execute.
        """
        # Auto-start/resume if needed
        if self._sandbox is None or self._is_paused:
            await self.start()

        if self._sandbox is None or self._is_paused:
            msg = "Failed to start sandbox"
            raise CLIError(msg)

        # Calculate effective timeout.
        # For unbounded commands (timeout=None), use BASH_MAX_TIMEOUT_MS as a
        # best-effort runway for _ensure_sandbox_ready, but omit the timeout
        # kwarg from the actual E2B commands.run() call.
        bounded = timeout is not None
        timeout_ms = min(timeout, BASH_MAX_TIMEOUT_MS) if timeout is not None else BASH_MAX_TIMEOUT_MS
        effective_timeout_s = timeout_ms / 1000

        # Ensure sandbox has enough time remaining.
        # This may mark the sandbox as paused if it expired or became unreachable.
        await self._ensure_sandbox_ready(effective_timeout_s)

        # Re-check: sandbox may have been marked paused by _ensure_sandbox_ready
        # (e.g. expired while idle, auto-paused by E2B). Try to reconnect.
        if self._sandbox is None or self._is_paused:
            await self.start()
        if self._sandbox is None or self._is_paused:
            msg = "Sandbox became unavailable and could not be reconnected"
            raise CLIError(msg)

        start_time = time.monotonic()

        from e2b import CommandExitException

        try:
            run_kwargs: dict[str, int] = {}
            if bounded:
                run_kwargs["timeout"] = int(effective_timeout_s)
            result = await self._sandbox.commands.run(
                command,
                **run_kwargs,
            )
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            exit_code = result.exit_code
        except CommandExitException as e:
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            exit_code = e.exit_code
        except Exception as e:
            # Check if it's a timeout
            if "timeout" in str(e).lower():
                msg = f"timed out after {effective_timeout_s}s"
                raise CLIError(msg) from None
            msg = f"Command execution failed: {e}"
            raise CLIError(msg) from e

        return CLIResult(
            stdout=stdout.removesuffix("\n"),
            stderr=stderr.removesuffix("\n"),
            exit_code=exit_code,
            metadata=ExecutionMetadata(duration_ms=int((time.monotonic() - start_time) * 1000)),
        )

    async def _ensure_sandbox_ready(self, command_timeout_s: float) -> None:
        """Ensure sandbox won't expire during command execution.

        Strategy:
            1. If sandbox is unreachable or expired: mark as paused for reconnection
            2. If enough time remains: do nothing
            3. If extending via set_timeout() stays within E2B's 1hr limit: extend
            4. If extending would exceed 1hr limit: pause and resume (~30s)

        Args:
            command_timeout_s: How long the command might take (seconds).
        """
        if self._sandbox is None or self._is_paused:
            return

        # Capture sandbox_id before any await — a concurrent run() on the
        # same event loop can set self._sandbox = None while we're waiting.
        sandbox_id = self._sandbox.sandbox_id

        try:
            info = await self._sandbox.get_info()
        except Exception as e:  # noqa: BLE001
            # Sandbox unreachable (killed, expired, network issue).
            # Mark as paused so the caller can reconnect via start().
            # Re-check: another concurrent task may have already handled this.
            if self._sandbox is None:
                return
            _logger.warning("Sandbox %s unreachable: %s", sandbox_id, e)
            self._sandbox_id = sandbox_id
            self._sandbox = None
            self._is_paused = True
            return

        # Re-check after await — another task may have cleared sandbox.
        if self._sandbox is None:
            return

        now = datetime.now(UTC)
        remaining_s = (info.end_at - now).total_seconds()

        if remaining_s <= 0:
            # Sandbox already expired or was auto-paused by E2B.
            _logger.warning(
                "Sandbox %s expired (%.0fs past end_at). Marking for reconnection.",
                sandbox_id,
                -remaining_s,
            )
            self._sandbox_id = sandbox_id
            self._sandbox = None
            self._is_paused = True
            return

        required_s = command_timeout_s + _SAFETY_BUFFER_S

        if remaining_s >= required_s:
            return

        # Not enough time remaining — decide between set_timeout() vs pause/resume
        elapsed_since_creation = (now - info.started_at).total_seconds()
        can_extend = (elapsed_since_creation + self._lifetime) <= _E2B_MAX_LIFETIME_S

        if can_extend:
            # set_timeout() is instant with no interruption
            _logger.info(
                "Sandbox %s has %.0fs remaining, need %.0fs. Extending timeout.",
                self._sandbox_id,
                remaining_s,
                required_s,
            )
            await self._sandbox.set_timeout(self._lifetime)
            _logger.info("Sandbox %s timeout extended", self._sandbox_id)
        else:
            # Would exceed E2B's 1hr hard limit — must pause/resume to reset clock
            _logger.warning(
                "Sandbox %s approaching E2B 1hr hard limit (%.0fs elapsed). Pausing and resuming to reset timer (~30s).",
                self._sandbox_id,
                elapsed_since_creation,
            )
            await self._pause_and_resume()

    async def _pause_and_resume(self) -> None:
        """Pause and immediately resume to reset E2B's timer.

        This is used when approaching the timeout limit to get a fresh
        time window while preserving all state.
        """
        if self._sandbox is None or self._is_paused:
            return

        sandbox_id = self._sandbox.sandbox_id

        # Pause
        try:
            await self._sandbox.beta_pause()
            self._sandbox = None  # Release stale SDK object (holds httpx client)
            self._sandbox_id = sandbox_id
            self._is_paused = True
        except Exception as e:
            _logger.exception("Failed to pause sandbox %s", sandbox_id)
            msg = f"Failed to pause sandbox for timer reset: {e}"
            raise CLIError(msg) from e

        # Resume immediately
        try:
            from e2b import AsyncSandbox

            self._sandbox = await AsyncSandbox.connect(
                sandbox_id,
                timeout=self._lifetime,
            )
            self._sandbox_id = sandbox_id
            self._is_paused = False
            _logger.info("Sandbox %s resumed with fresh timer", sandbox_id)
        except Exception as e:
            _logger.exception("Failed to resume sandbox %s", sandbox_id)
            # Sandbox is still paused on E2B — preserve ID so caller can retry
            self._sandbox_id = sandbox_id
            self._is_paused = True
            msg = f"Failed to resume sandbox after pause: {e}"
            raise CLIError(msg) from e


_: type[Computer] = RemoteE2BComputer
