"""Local VM — a shared VM that hands out isolated session computers.

``LocalVM`` owns:
- VM lifecycle (start/stop via LimaVM)
- Mount state (lima.yaml is the single source of truth)
- Session lifecycle (create/destroy Linux users)

Users call :meth:`LocalVM.computer` to get a ``Computer`` handle bound
to an isolated Linux user on the VM.
"""

from __future__ import annotations

import asyncio
import shlex
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import petname

from openagent.computer.base import (
    BASH_MAX_TIMEOUT_MS,
    SESSION_DIRS,
    SESSION_OUTPUTS_DIR,
    SESSION_TMP_DIR,
    AsyncComputerMixin,
    Computer,
    Mount,
)
from openagent.computer.local._types import ResolvedMount
from openagent.exceptions import CLIError, UnsupportedPlatformError, VMError, VMMountConflictError

if TYPE_CHECKING:
    from openagent.computer.local._lima import LimaVM
    from openagent.types import CLIResult


# ------------------------------------------------------------------
# Session handle (internal)
# ------------------------------------------------------------------


class _VMSessionComputer(AsyncComputerMixin):
    """Session-scoped execution handle on a shared VM.

    Created by :meth:`LocalVM.computer`. Do not instantiate directly.

    Parameters:
        vm: The VM backend for shell/copy operations.
        session_name: Linux username for this session.
    """

    def __init__(self, *, vm: LimaVM, session_name: str) -> None:
        """Initialize with a VM backend and session name."""
        self._vm = vm
        self._session_name = session_name
        self._active = True

    @property
    def session_name(self) -> str:
        """Session name (Linux username on the VM)."""
        return self._session_name

    @property
    def is_running(self) -> bool:
        """True if this handle is active."""
        return self._active

    async def start(self) -> None:
        """Health check — verify the VM is running and session user exists.

        Does NOT start the VM or create sessions.
        """
        if self._active:
            return
        # Re-activate after stop
        status = await self._vm.status()
        if status != "Running":
            msg = "VM is not running"
            raise CLIError(msg)
        result = await self._vm.shell(f"id -u {self._session_name}")
        if result.exit_code != 0:
            msg = f"Session '{self._session_name}' does not exist on the VM"
            raise CLIError(msg)
        self._active = True

    async def stop(self) -> None:
        """Mark this handle as inactive. Does NOT stop the VM."""
        self._active = False

    async def run(
        self,
        command: str,
        *,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> CLIResult:
        """Execute a command as the session user.

        Args:
            command: Shell command to run.
            timeout: Timeout in milliseconds (Computer protocol).

        Returns:
            CLIResult with stdout, stderr, exit_code, and metadata.
        """
        self._check_active()
        timeout_ms = min(timeout, BASH_MAX_TIMEOUT_MS) if timeout is not None else BASH_MAX_TIMEOUT_MS
        try:
            return await self._vm.shell(
                command,
                user=self._session_name,
                timeout=timeout_ms / 1000,
            )
        except VMError as e:
            raise CLIError(str(e)) from e

    async def upload(self, src: str, dst: str) -> None:
        """Transfer a file from the host to the VM session."""
        self._check_active()
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
            # Copy to /tmp first (always writable), then sudo mv into place.
            # This works regardless of destination directory ownership.
            tmp = f"/tmp/.upload-{uuid.uuid4().hex}"  # noqa: S108
            await self._vm.copy(src, tmp, host_to_guest=True)
            await self._vm.shell(
                f"sudo mv {tmp} {shlex.quote(dst)} && "
                f"sudo chown {self._session_name}:{self._session_name} {shlex.quote(dst)} && "
                f"sudo chmod 644 {shlex.quote(dst)}"
            )
        except VMError as e:
            raise CLIError(str(e)) from e

    async def download(self, src: str, dst: str) -> None:
        """Transfer a file from the VM session to the host.

        ``limactl copy`` runs as the default Lima SSH user which cannot
        read files owned by the session user.  Work around this by
        sudo-copying the file to a world-readable temp location first,
        then pulling it to the host, mirroring the strategy used by
        :meth:`upload`.
        """
        self._check_active()
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        tmp = f"/tmp/.download-{uuid.uuid4().hex}"  # noqa: S108
        try:
            result = await self._vm.shell(f"sudo cp {shlex.quote(src)} {tmp} && sudo chmod 644 {tmp}")
            if result.exit_code != 0:
                msg = result.stderr or result.stdout or f"Failed to stage {src} for download"
                raise CLIError(msg)
            await self._vm.copy(tmp, dst, host_to_guest=False)
        except VMError as e:
            raise CLIError(str(e)) from e
        finally:
            # Best-effort cleanup of the temp file inside the guest.
            await self._vm.shell(f"sudo rm -f {tmp}")

    def _check_active(self) -> None:
        """Raise if handle is inactive."""
        if not self._active:
            msg = "Computer handle is inactive — call start() to reactivate"
            raise CLIError(msg)


# Protocol compliance assertion
_: type[Computer] = _VMSessionComputer


# ------------------------------------------------------------------
# Mount helpers
# ------------------------------------------------------------------


def _mount_set(mounts: list[ResolvedMount]) -> set[tuple[str, str, bool]]:
    """Convert a list of resolved mounts to a comparable set."""
    return {(m.host_path, m.guest_path, m.writable) for m in mounts}


# ------------------------------------------------------------------
# LocalVM
# ------------------------------------------------------------------


class LocalVM:
    """A shared VM that hands out isolated session computers.

    Mount state lives in ``lima.yaml`` (the single source of truth).
    All mount/unmount operations read from and write to lima.yaml
    directly — no in-memory mount tracking.

    Parameters:
        instance: Lima VM instance name.
    """

    def __init__(self, *, instance: str = "openagent") -> None:
        """Initialize with a Lima VM instance name."""
        if sys.platform == "darwin":
            from openagent.computer.local._lima import LimaVM as _LimaVM

            self._vm: LimaVM = _LimaVM(instance=instance)
        else:
            msg = f"LocalVM is not supported on {sys.platform}"
            raise UnsupportedPlatformError(msg)

        self._instance = instance
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Ensure the VM is running. Idempotent."""
        if await self._vm.status() == "Running":
            return
        await self._vm.start()

    async def stop(self) -> None:
        """Stop the VM. Idempotent."""
        if await self._vm.status() != "Running":
            return
        await self._vm.stop()

    async def mount(
        self,
        mounts: Mount | list[Mount],
        *,
        session: str | None = None,
        defer: bool = False,
    ) -> None:
        """Add one or more mounts to the VM.

        Idempotent: mounts already present in lima.yaml (same host path,
        guest path, and writable flag) are silently skipped.

        Args:
            mounts: A single mount or list of mounts to add.
            session: Target session name. ``None`` = system scope (``/mnt/``).
            defer: If ``True``, update lima.yaml but skip the VM restart.
                Call :meth:`apply` later to apply all deferred changes in
                a single restart.

        Raises:
            ValueError: Invalid mount source.
            VMMountConflictError: Guest path conflict with different config.
            VMError: Session does not exist on the VM.
        """
        mount_list = [mounts] if isinstance(mounts, Mount) else list(mounts)
        if not mount_list:
            return

        self._validate_mounts(mount_list)

        # Validate session user exists on the VM
        if session is not None:
            result = await self._vm.shell(f"id -u {shlex.quote(session)}")
            if result.exit_code != 0:
                msg = f"Session '{session}' does not exist on the VM"
                raise VMError(msg)

        scope = "session" if session is not None else "system"
        resolved_new = [self._resolve_mount(m, scope=scope, session_name=session) for m in mount_list]

        # Within-batch conflict check
        self._check_conflicts(resolved_new, scope_label=session or "system")

        async with self._lock:
            # Read existing mounts from lima.yaml (authoritative)
            existing = self._vm.read_mounts()
            existing_set = _mount_set(existing)

            # Filter out already-present mounts (idempotent)
            truly_new = [r for r in resolved_new if (r.host_path, r.guest_path, r.writable) not in existing_set]
            if not truly_new:
                return

            # Collision check: same guest path but different config
            existing_guests = {r.guest_path for r in existing}
            for r in truly_new:
                if r.guest_path in existing_guests:
                    msg = f"Mount conflict: guest path '{r.guest_path}' is already in use"
                    raise VMMountConflictError(msg)

            # Merge existing + new
            merged = existing + truly_new
            if defer:
                self._vm.write_mounts(merged)
            else:
                await self._vm.apply_mounts(merged)

    async def unmount(
        self,
        targets: str | list[str],
        *,
        session: str | None = None,
        defer: bool = False,
    ) -> None:
        """Remove one or more mounts by target path.

        Idempotent: targets not found in lima.yaml are silently skipped.

        Args:
            targets: A single target or list of targets to remove.
            session: Scope. ``None`` = system.
            defer: If ``True``, update lima.yaml but skip the VM restart.
                The mount disappears from the config immediately (so
                conflict checks stay correct) but remains active in the
                running VM until the next restart.
        """
        target_list = [targets] if isinstance(targets, str) else list(targets)
        if not target_list:
            return

        # Resolve targets to guest paths
        scope = "session" if session is not None else "system"
        guest_paths_to_remove = {self._target_to_guest(t, scope=scope, session_name=session) for t in target_list}

        async with self._lock:
            # Read existing from lima.yaml
            existing = self._vm.read_mounts()
            remaining = [m for m in existing if m.guest_path not in guest_paths_to_remove]

            if len(remaining) == len(existing):
                return  # Nothing to remove (idempotent)

            if defer:
                self._vm.write_mounts(remaining)
            else:
                await self._vm.apply_mounts(remaining)

    def list_mounts(self, *, session: str | None = None) -> list[ResolvedMount]:
        """Return mounts from lima.yaml (the source of truth).

        Args:
            session: If given, filter to that session's mounts only.
                ``None`` returns all mounts.

        Returns:
            Resolved mounts currently configured in the VM.
        """
        all_mounts = self._vm.read_mounts()
        if session is not None:
            prefix = f"/sessions/{session}/"
            return [m for m in all_mounts if m.guest_path.startswith(prefix)]
        return all_mounts

    async def apply(self) -> None:
        """Apply deferred mount/unmount changes by restarting the VM.

        Call this after one or more ``mount(defer=True)`` or
        ``unmount(defer=True)`` operations to flush all pending config
        changes in a single VM restart.

        If the VM is not running, starts it (picking up the new config).
        If it is running, stops then starts it.

        Raises:
            VMError: If the VM instance does not exist.
        """
        async with self._lock:
            status = await self._vm.status()
            if status is None:
                msg = f"VM instance '{self._instance}' does not exist"
                raise VMError(msg)
            if status == "Running":
                await self._vm.stop()
            await self._vm.start()

    async def computer(
        self,
        *,
        mounts: list[Mount] | None = None,
        resume: str | None = None,
    ) -> _VMSessionComputer:
        """Create a new session computer or resume an existing one.

        Args:
            mounts: Host directories to mount for this session.
            resume: Session name to reconnect to.

        Returns:
            A ``Computer`` handle bound to the session.

        Raises:
            ValueError: Both mounts and resume specified, or invalid mounts.
            VMError: Session creation or resume failed.
        """
        if resume is not None and mounts:
            msg = "Cannot specify 'mounts' when resuming a session"
            raise ValueError(msg)

        if await self._vm.status() != "Running":
            await self.start()

        if resume is not None:
            # Validate session exists on VM
            result = await self._vm.shell(f"id -u {shlex.quote(resume)}")
            if result.exit_code != 0:
                msg = f"Session '{resume}' does not exist on the VM"
                raise VMError(msg)
            name = resume
        else:
            # Create new session
            name = await self._generate_unique_name()
            await self._create_user(name)

            if mounts:
                try:
                    await self.mount(mounts, session=name)
                except Exception:
                    # Rollback: remove orphaned user
                    await self._vm.shell(f"sudo userdel -r {shlex.quote(name)}")
                    raise

        return _VMSessionComputer(vm=self._vm, session_name=name)

    async def destroy(self, name: str) -> None:
        """Delete a session user and its mounts.

        Args:
            name: Session name to destroy.
        """
        if await self._vm.status() != "Running":
            await self.start()

        await self._vm.shell(f"sudo userdel -r {shlex.quote(name)}")

        # Remove all session mounts from lima.yaml
        async with self._lock:
            existing = self._vm.read_mounts()
            prefix = f"/sessions/{name}/"
            remaining = [m for m in existing if not m.guest_path.startswith(prefix)]

            if len(remaining) != len(existing):
                await self._vm.apply_mounts(remaining)

    async def list_sessions(self) -> list[str]:
        """List active sessions on the VM."""
        if await self._vm.status() != "Running":
            msg = "VM is not running — call start() first"
            raise VMError(msg)
        result = await self._vm.shell("ls /sessions/")
        if result.exit_code != 0 or not result.stdout.strip():
            return []
        return result.stdout.strip().split()

    # ------------------------------------------------------------------
    # Mount resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_mount(
        mount: Mount,
        scope: str,
        session_name: str | None = None,
    ) -> ResolvedMount:
        """Resolve a Mount to a concrete guest path."""
        guest = LocalVM._target_to_guest(mount.target, scope, session_name)
        return ResolvedMount(
            host_path=mount.source,
            guest_path=guest,
            writable=mount.writable,
        )

    @staticmethod
    def _target_to_guest(
        target: str,
        scope: str,
        session_name: str | None = None,
    ) -> str:
        """Compute the guest path for a mount target."""
        if target.startswith("/"):
            return target
        if scope == "system":
            return f"/mnt/{target}"
        return f"/sessions/{session_name}/mnt/{target}"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_mounts(mounts: list[Mount]) -> None:
        """Validate mount sources exist and are directories."""
        for mount in mounts:
            p = Path(mount.source)
            if not p.exists():
                msg = f"Mount source does not exist: {mount.source}"
                raise ValueError(msg)
            if not p.is_dir():
                msg = f"Mount source is not a directory: {mount.source}"
                raise ValueError(msg)

    @staticmethod
    def _check_conflicts(resolved: list[ResolvedMount], scope_label: str) -> None:
        """Reject duplicate guest paths within a batch."""
        seen: dict[str, str] = {}  # guest_path -> host_path
        for m in resolved:
            if m.guest_path in seen:
                msg = f"Mount conflict in {scope_label}: '{m.host_path}' and '{seen[m.guest_path]}' both target '{m.guest_path}'"
                raise VMMountConflictError(msg)
            seen[m.guest_path] = m.host_path

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _generate_unique_name(self, max_attempts: int = 5) -> str:
        """Generate a unique petname not colliding with existing VM users."""
        for _ in range(max_attempts):
            name: str = petname.generate(words=3, letters=10)
            result = await self._vm.shell(f"id -u {shlex.quote(name)}")
            if result.exit_code != 0:
                return name
        msg = f"Failed to generate a unique session name after {max_attempts} attempts"
        raise VMError(msg)

    async def _create_user(self, name: str) -> None:
        """Create a Linux user with standard session directories."""
        qname = shlex.quote(name)
        home = f"/sessions/{name}"
        qhome = shlex.quote(home)
        result = await self._vm.shell(f"sudo useradd -m -d {qhome} -s /bin/bash --no-log-init -K SUB_UID_COUNT=0 -K SUB_GID_COUNT=0 {qname}")
        if result.exit_code != 0:
            msg = f"Failed to create session user '{name}': {result.stderr}"
            raise VMError(msg)

        # Create all dirs as root, then chown only the writable ones.
        # uploads stays root-owned (read-only), outputs is user-writable.
        all_dirs = " ".join(shlex.quote(f"{home}/{d}") for d in SESSION_DIRS)
        writable = f"{shlex.quote(f'{home}/{SESSION_TMP_DIR}')} {shlex.quote(f'{home}/{SESSION_OUTPUTS_DIR}')}"
        result = await self._vm.shell(f"sudo mkdir -p {all_dirs} && sudo chown {qname} {writable}")
        if result.exit_code != 0:
            msg = f"Failed to create session directories for '{name}': {result.stderr}"
            raise VMError(msg)
