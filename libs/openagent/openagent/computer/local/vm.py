"""Local VM computer — an isolated session on a platform-specific VM.

Each ``LocalVMComputer`` is an isolated session backed by a unique Linux user
on a shared VM. Commands run in the session user's home directory
at ``/sessions/<petname>/``.

The VM backend is selected automatically based on the host platform:
- macOS: Lima VM (requires ``limactl``)
- Windows: (coming soon)
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import petname

from openagent.computer.base import (
    BASH_MAX_TIMEOUT_MS,
    SESSION_DIRS,
    AsyncComputerMixin,
    Computer,
)
from openagent.exceptions import CLIError, UnsupportedPlatformError, VMError

if TYPE_CHECKING:
    from openagent.computer.local._lima import LimaVM, Mount
    from openagent.types import CLIResult


def _create_vm(instance: str) -> LimaVM:
    """Create the platform-appropriate VM backend."""
    if sys.platform == "darwin":
        from openagent.computer.local._lima import LimaVM

        return LimaVM(instance=instance)

    msg = f"LocalVMComputer is currently not supported on {sys.platform}"
    raise UnsupportedPlatformError(msg)


class LocalVMComputer(AsyncComputerMixin):
    """An isolated session on a platform-specific VM.

    The VM backend is selected automatically based on the host OS:
    - macOS → Lima VM
    - Windows → (coming soon)

    Each instance gets an isolated Linux user on the VM.

    The session's home directory is ``/sessions/<name>/`` and host mounts
    appear at ``/sessions/<name>/mnt/<basename>``.

    Parameters:
        instance: VM instance name (default ``"openagent"``).
        resume: Name of an existing session to reconnect to.
            When ``None`` (default), a new session with an
            auto-generated name is created.
        mounts: Host paths to mount into the session (new sessions only).
    """

    def __init__(
        self,
        *,
        instance: str = "openagent",
        resume: str | None = None,
        mounts: list[str] | None = None,
    ) -> None:
        """Initialize a LocalVMComputer.

        Args:
            instance: VM instance name.
            resume: Name of an existing session to reconnect to.
            mounts: Host paths to mount into the session (new sessions only).
        """
        if resume is not None and mounts:
            msg = "Cannot specify 'mounts' when resuming a session"
            raise ValueError(msg)

        for mount in mounts or []:
            p = Path(mount)
            if not p.exists():
                msg = f"Mount path does not exist: {mount}"
                raise ValueError(msg)
            if not p.is_dir():
                msg = f"Mount path is not a directory: {mount}"
                raise ValueError(msg)

        self._vm = _create_vm(instance)
        self._resume = resume
        self._mounts = mounts or []
        self._session_name: str | None = None
        self._started = False
        self._session_initialized = False

    @property
    def session_name(self) -> str | None:
        """Session name, or ``None`` until ``start()`` succeeds."""
        return self._session_name

    @property
    def is_running(self) -> bool:
        """Return True if the session is started."""
        return self._started

    async def start(self) -> None:
        """Start the session. Creates the user on first call, restarts the VM on subsequent calls."""
        if self._started:
            return

        if not self._session_initialized:
            await self._initialize_session()
            self._session_initialized = True
        else:
            # Restart after stop — session user persists on disk.
            # Mounts persist in VM config from first start.
            await self._vm.start()

        self._started = True

    async def _initialize_session(self) -> None:
        """First-time session setup: create or resume user, configure mounts."""
        await self._vm.start()

        if self._resume is not None:
            # Resume existing session — must exist
            result = await self._vm.shell(f"id -u {self._resume}")
            if result.exit_code != 0:
                msg = f"Session '{self._resume}' does not exist on the VM"
                raise VMError(msg)
            self._session_name = self._resume
        else:
            # New session with auto-generated name
            name = await self._generate_unique_name()
            await self._create_user(name)
            self._session_name = name

        # Configure mounts if any
        if self._mounts:
            mount_objs = [self._make_mount(path) for path in self._mounts]
            # Stops + restarts VM with mounts
            await self._vm.start(mounts=mount_objs)

    def _make_mount(self, path: str) -> Mount:
        """Create a mount object for the current VM backend."""
        if sys.platform == "darwin":
            from openagent.computer.local._lima import Mount

            return Mount(
                location=path,
                mount_point=f"/sessions/{self._session_name}/mnt/{Path(path).name}",
                writable=True,
            )

        msg = f"Mounts not supported on {sys.platform}"
        raise UnsupportedPlatformError(msg)

    async def _generate_unique_name(self, max_attempts: int = 5) -> str:
        """Generate a unique petname that doesn't collide with existing users."""
        for _ in range(max_attempts):
            name: str = petname.generate(words=3, letters=10)
            result = await self._vm.shell(f"id -u {name}")
            if result.exit_code != 0:
                return name
        msg = f"Failed to generate a unique session name after {max_attempts} attempts"
        raise VMError(msg)

    async def _create_user(self, name: str) -> None:
        """Create the Linux user and standard session directories."""
        home = f"/sessions/{name}"
        result = await self._vm.shell(f"sudo useradd -m -d {home} -s /bin/bash --no-log-init -K SUB_UID_COUNT=0 -K SUB_GID_COUNT=0 {name}")
        if result.exit_code != 0:
            msg = f"Failed to create session user '{name}': {result.stderr}"
            raise VMError(msg)

        dirs = " ".join(f"{home}/{d}" for d in SESSION_DIRS)
        result = await self._vm.shell(f"sudo mkdir -p {dirs} && sudo chown -R {name} {dirs}")
        if result.exit_code != 0:
            msg = f"Failed to create session directories for '{name}': {result.stderr}"
            raise VMError(msg)

    async def upload(self, src: str, dst: str) -> None:
        """Transfer a file from the host to the VM session.

        Creates parent directories on the guest and sets ownership
        to the session user.
        """
        if not self._started:
            await self.start()

        src_path = Path(src)
        if not src_path.exists():
            msg = f"Source file not found: {src}"
            raise FileNotFoundError(msg)
        if not src_path.is_file():
            msg = f"Source is not a file: {src}"
            raise CLIError(msg)

        dst_parent = str(Path(dst).parent)
        try:
            await self._vm.shell(f"sudo mkdir -p {shlex.quote(dst_parent)}")
            await self._vm.copy(src, dst, host_to_guest=True)
            await self._vm.shell(f"sudo chown {self._session_name} {shlex.quote(dst)}")
        except VMError as e:
            raise CLIError(str(e)) from e

    async def download(self, src: str, dst: str) -> None:
        """Transfer a file from the VM session to the host.

        Creates parent directories on the host.
        """
        if not self._started:
            await self.start()

        Path(dst).parent.mkdir(parents=True, exist_ok=True)

        try:
            await self._vm.copy(src, dst, host_to_guest=False)
        except VMError as e:
            raise CLIError(str(e)) from e

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> CLIResult:
        """Execute a command as the session user.

        Auto-starts if needed. Timeout is in milliseconds (Computer protocol),
        converted to seconds for the VM shell.
        """
        if not self._started:
            await self.start()

        # Normalize timeout (ms) with max cap
        timeout_ms = min(timeout, BASH_MAX_TIMEOUT_MS) if timeout is not None else BASH_MAX_TIMEOUT_MS
        effective_timeout_secs = timeout_ms / 1000

        try:
            return await self._vm.shell(
                command,
                user=self._session_name,
                timeout=effective_timeout_secs,
            )
        except VMError as e:
            raise CLIError(str(e)) from e

    async def stop(self) -> None:
        """Stop the VM. Session state is preserved for restart."""
        if not self._started:
            return

        await self._vm.stop()
        self._started = False
        # _session_initialized and _session_name preserved — start() restarts
        # without recreating the session

    async def delete_session(self) -> None:
        """Delete the session user and home directory from the VM."""
        if self._session_name is None:
            return

        # Ensure VM is running
        await self._vm.start()

        name = self._session_name
        await self._vm.shell(f"sudo userdel -r {name}")

        self._session_name = None
        self._session_initialized = False
        self._started = False

    async def list_sessions(self) -> list[str]:
        """List all session directories on the VM.

        Raises:
            VMError: If the VM is not running.
        """
        if not self._started:
            msg = "VM is not running — call start() first"
            raise VMError(msg)

        result = await self._vm.shell("ls /sessions/")
        if result.exit_code != 0 or not result.stdout.strip():
            return []
        return result.stdout.strip().split()


_: type[Computer] = LocalVMComputer
