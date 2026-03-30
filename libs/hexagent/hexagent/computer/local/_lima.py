"""Lima VM instance management via limactl.

Manages the lifecycle of a Lima VM (create, start, stop, delete, shell).
This is infrastructure — not a Computer implementation. Session management
lives in ``LocalVM``.

Lifecycle commands (``build``, ``start``, ``stop``, ``apply_mounts``) let
``limactl`` run to completion.  ``limactl start`` blocks internally until
the VM is Running, boot scripts finish, and the guest agent is alive — no
manual polling required.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import shutil
import sys
import time
from pathlib import Path

import yaml

from hexagent.computer.base import ExecutionMetadata
from hexagent.computer.local._types import ResolvedMount
from hexagent.exceptions import LimaError, MissingDependencyError, UnsupportedPlatformError
from hexagent.types import CLIResult


class LimaVM:
    """Manages a single Lima VM instance.

    Parameters:
        instance: Lima instance name.
    """

    _instance: str

    def __init__(self, instance: str) -> None:
        if sys.platform != "darwin":
            msg = f"Lima is a macOS hypervisor — it cannot run on {sys.platform}"
            raise UnsupportedPlatformError(msg)
        if not shutil.which("limactl"):
            msg = "limactl not found. Install Lima: https://lima-vm.io"
            raise MissingDependencyError(msg)
        self._instance = instance

    @property
    def instance(self) -> str:
        """Read-only Lima instance name."""
        return self._instance

    @property
    def _yaml_path(self) -> Path:
        """Path to ``lima.yaml`` for this instance."""
        lima_home = Path(os.environ.get("LIMA_HOME", Path.home() / ".lima"))
        return lima_home / self._instance / "lima.yaml"

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self) -> str | None:
        """Return the instance status string, or ``None`` if it doesn't exist."""
        proc = await asyncio.create_subprocess_exec(
            "limactl",
            "list",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()

        if proc.returncode != 0:
            return None

        for line in stdout_bytes.decode("utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if entry.get("name") == self._instance:
                status: str | None = entry.get("status")
                return status

        return None

    # ------------------------------------------------------------------
    # Mount inspection
    # ------------------------------------------------------------------

    def read_mounts(self) -> list[ResolvedMount]:
        """Read the current mount configuration from lima.yaml.

        Parses ``$LIMA_HOME/<instance>/lima.yaml`` (default ``~/.lima``)
        and returns the ``.mounts`` array as ``ResolvedMount`` objects.

        Returns:
            List of resolved mounts currently configured in the VM.
            Empty list if the file doesn't exist or has no mounts.
        """
        yaml_path = self._yaml_path
        if not yaml_path.exists():
            return []

        with yaml_path.open("r", encoding="utf-8") as f:
            data: dict[str, object] = yaml.safe_load(f) or {}

        raw_mounts = data.get("mounts", [])
        if not isinstance(raw_mounts, list):
            return []

        result: list[ResolvedMount] = []
        for entry in raw_mounts:
            if not isinstance(entry, dict):
                continue
            location = entry.get("location")
            mount_point = entry.get("mountPoint")
            if location is None or mount_point is None:
                continue
            result.append(
                ResolvedMount(
                    host_path=str(location),
                    guest_path=str(mount_point),
                    writable=bool(entry.get("writable", False)),
                )
            )
        return result

    def write_mounts(self, mounts: list[ResolvedMount]) -> None:
        """Write mount configuration to lima.yaml without restarting the VM.

        Updates the ``.mounts`` section in-place.  The change takes effect
        on the next VM restart (manual or via ``apply_mounts``).

        Note: this bypasses ``limactl edit`` (which refuses running
        instances) deliberately — it is used for deferred config updates
        that should not trigger a restart.

        Raises:
            LimaError: If the lima.yaml file does not exist.
        """
        yaml_path = self._yaml_path
        if not yaml_path.exists():
            msg = f"lima.yaml not found for instance '{self._instance}'"
            raise LimaError(msg)

        with yaml_path.open("r", encoding="utf-8") as f:
            data: dict[str, object] = yaml.safe_load(f) or {}

        data["mounts"] = [{"location": m.host_path, "mountPoint": m.guest_path, "writable": m.writable} for m in mounts]

        with yaml_path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def build(self, yaml_path: Path | str) -> None:
        """Create and provision a new VM instance from a YAML config.

        Blocks until the VM is fully ready (image downloaded, provisioned,
        boot scripts complete, guest agent alive).

        Raises ``LimaError`` if the instance already exists.
        """
        current = await self.status()
        if current is not None:
            msg = f"Lima instance '{self._instance}' already exists (status: {current})"
            raise LimaError(msg)

        await self._run_limactl(
            "limactl",
            "start",
            f"--name={self._instance}",
            str(yaml_path),
            "--tty=false",
            timeout=600,
        )

    async def start(self) -> None:
        """Start the VM instance.

        Blocks until the VM is Running, boot scripts finish, and the
        guest agent is alive.  No-op if already running.

        Raises ``LimaError`` if the instance doesn't exist.
        """
        current = await self.status()

        if current is None:
            msg = f"Lima instance '{self._instance}' does not exist. Create it first with build()."
            raise LimaError(msg)

        if current == "Running":
            return

        await self._run_limactl(
            "limactl",
            "start",
            self._instance,
            "--tty=false",
            timeout=300,
        )

    async def apply_mounts(self, mounts: list[ResolvedMount]) -> None:
        """Apply mount configuration to the VM.

        Stops the VM (if running), updates the mount config via
        ``--set``, and starts it again.  Blocks until fully ready.

        Args:
            mounts: Complete list of resolved mounts. Replaces all
                existing mounts in lima.yaml.

        Raises:
            LimaError: If the instance does not exist or start fails.
        """
        current = await self.status()
        if current is None:
            msg = f"Lima instance '{self._instance}' does not exist"
            raise LimaError(msg)
        if current == "Running":
            await self.stop()

        mount_set = self._build_mount_set_arg(mounts)
        await self._run_limactl(
            "limactl",
            "start",
            self._instance,
            "--tty=false",
            "--set",
            mount_set,
            timeout=300,
        )

    async def stop(self) -> None:
        """Stop the VM instance.

        Blocks until the host agent exits and the VM reaches Stopped
        status.  No-op if already stopped.

        Raises:
            LimaError: If the stop command fails.
        """
        current = await self.status()
        if current is None or current != "Running":
            return

        await self._run_limactl(
            "limactl",
            "stop",
            self._instance,
            timeout=240,
        )

    async def delete(self) -> None:
        """Delete the VM instance forcefully (best-effort)."""
        with contextlib.suppress(LimaError):
            await self._run_limactl(
                "limactl",
                "delete",
                "--force",
                self._instance,
            )

    # ------------------------------------------------------------------
    # Shell execution
    # ------------------------------------------------------------------

    async def shell(
        self,
        command: str,
        *,
        user: str | None = None,
        cwd: str | None = None,
        timeout: float | None = None,  # noqa: ASYNC109
        input: str | None = None,
    ) -> CLIResult:
        """Execute a command inside the VM via ``limactl shell``.

        Parameters:
            command: Shell command to run.
            user: If set, run as this Linux user via ``sudo -u`` with login shell.
            cwd: Working directory inside the VM. For session users without
                explicit cwd, defaults to ``cd`` (home directory).
            timeout: Timeout in **seconds**. ``None`` means wait indefinitely.
            input: Optional stdin to pass to the command.

        Returns:
            CLIResult with stdout, stderr, exit_code, and metadata.

        Raises:
            LimaError: On timeout or subprocess failure.
        """
        if user is not None:
            escaped = command.replace("'", r"'\''")
            cd_part = f"cd {shlex.quote(cwd)}" if cwd is not None else "cd"
            inner = f"sudo -u {shlex.quote(user)} -H bash -l -c '{cd_part} && {escaped}'"
        elif cwd is not None:
            inner = f"cd {shlex.quote(cwd)} && {command}"
        else:
            inner = command

        exec_args = [
            "limactl",
            "shell",
            "--workdir",
            "/",
            self._instance,
            "bash",
            "-c",
            inner,
        ]

        start_time = time.monotonic()

        process = await asyncio.create_subprocess_exec(
            *exec_args,
            stdin=asyncio.subprocess.PIPE if input is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=input.encode() if input is not None else None),
                timeout=timeout,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            msg = f"timed out after {timeout}s"
            raise LimaError(msg) from None

        stdout = stdout_bytes.decode("utf-8", errors="replace").removesuffix("\n")
        stderr = stderr_bytes.decode("utf-8", errors="replace").removesuffix("\n")

        # returncode is always set after communicate()
        rc: int = process.returncode if process.returncode is not None else -1
        return CLIResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=rc,
            metadata=ExecutionMetadata(duration_ms=int((time.monotonic() - start_time) * 1000)),
        )

    # ------------------------------------------------------------------
    # File transfer
    # ------------------------------------------------------------------

    async def copy(self, src: str, dst: str, *, host_to_guest: bool) -> None:
        """Copy a file between host and guest via ``limactl copy``.

        Args:
            src: Source path (host path if host_to_guest, else guest path).
            dst: Destination path (guest path if host_to_guest, else host path).
            host_to_guest: Direction of the copy.

        Raises:
            LimaError: If the copy fails.
        """
        if host_to_guest:
            copy_src = src
            copy_dst = f"{self._instance}:{dst}"
        else:
            copy_src = f"{self._instance}:{src}"
            copy_dst = dst

        await self._run_limactl("limactl", "copy", copy_src, copy_dst)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_limactl(self, *cmd: str, timeout: float = 300) -> str:  # noqa: ASYNC109
        """Run a limactl command to completion.

        Args:
            *cmd: Command and arguments.
            timeout: Maximum seconds to wait. Defaults to 5 minutes.

        Returns:
            Decoded stdout.

        Raises:
            LimaError: On non-zero exit code or timeout.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            msg = f"limactl timed out after {timeout}s: {' '.join(cmd[:3])}"
            raise LimaError(msg) from None

        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            msg = f"limactl failed (exit {proc.returncode}): {stderr}"
            raise LimaError(msg)

        return stdout_bytes.decode("utf-8", errors="replace")

    @staticmethod
    def _build_mount_set_arg(mounts: list[ResolvedMount]) -> str:
        """Build the ``--set`` value for Lima mount configuration."""
        entries = [{"location": m.host_path, "mountPoint": m.guest_path, "writable": m.writable} for m in mounts]
        return f".mounts = {json.dumps(entries)}"
