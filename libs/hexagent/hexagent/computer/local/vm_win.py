"""Local VM (Windows) — a shared WSL2 distro that hands out isolated session computers.

.. note:: **Merge-readiness**

   This module duplicates the structure of ``vm.py`` (the macOS variant)
   with ``WslVM`` swapped in for ``LimaVM``.  When both platforms have
   stabilised, unify by:

   1. Extract a ``VMBackend`` Protocol with the shared method surface
      (``status``, ``start``, ``stop``, ``shell``, ``copy``,
      ``read_mounts``, ``write_mounts``, ``apply_mounts``).
   2. Have both ``LimaVM`` and ``WslVM`` implement it.
   3. Make ``vm.py`` generic over the backend via platform dispatch
      in ``LocalVM.__init__``.
   4. Delete this file.

``LocalVM`` owns:

- VM lifecycle (start/stop via WslVM)
- Mount state (mounts.json is the single source of truth)
- Session lifecycle (create/destroy Linux users)

Users call :meth:`LocalVM.computer` to get a ``Computer`` handle bound
to an isolated Linux user on the WSL distro.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import petname

from hexagent.computer.base import (
    BASH_MAX_TIMEOUT_MS,
    SESSION_DIRS,
    SESSION_OUTPUTS_DIR,
    SESSION_TMP_DIR,
    AsyncComputerMixin,
    Computer,
    Mount,
)
from hexagent.computer.local._types import ResolvedMount
from hexagent.exceptions import CLIError, VMError, VMMountConflictError

if TYPE_CHECKING:
    from hexagent.computer.local._wsl import WslVM
    from hexagent.types import CLIResult


# ------------------------------------------------------------------
# Session handle (internal)
# ------------------------------------------------------------------
# MERGE NOTE: This class is functionally identical to
# ``vm._VMSessionComputer``.  The only difference is the type
# annotation on ``vm`` (``WslVM`` here vs ``LimaVM`` in ``vm.py``).
# Once a ``VMBackend`` Protocol is extracted, a single
# ``_VMSessionComputer`` parameterised on that Protocol will serve
# both platforms.
# ------------------------------------------------------------------


class _VMSessionComputer(AsyncComputerMixin):
    """Session-scoped execution handle on a shared WSL2 distro.

    Created by :meth:`LocalVM.computer`. Do not instantiate directly.

    Parameters:
        vm: The WSL VM backend for shell/copy operations.
        session_name: Linux username for this session.
    """

    def __init__(self, *, vm: WslVM, session_name: str, default_cwd: str | None = None) -> None:
        """Initialize with a VM backend and session name."""
        self._vm = vm
        self._session_name = session_name
        self._active = True
        self._default_cwd = default_cwd

    @property
    def session_name(self) -> str:
        """Session name (Linux username on the distro)."""
        return self._session_name

    @property
    def is_running(self) -> bool:
        """True if this handle is active."""
        return self._active

    def set_default_cwd(self, cwd: str | None) -> None:
        """Set the default working directory for future commands."""
        self._default_cwd = cwd

    async def start(self) -> None:
        """Health check — verify the distro is running and session user exists.

        Does NOT start the distro or create sessions.
        """
        if self._active:
            return
        status = await self._vm.status()
        if status != "Running":
            msg = "WSL distro is not running"
            raise CLIError(msg)
        result = await self._vm.shell(f"id -u {self._session_name}")
        if result.exit_code != 0:
            msg = f"Session '{self._session_name}' does not exist on the distro"
            raise CLIError(msg)
        self._active = True

    async def stop(self) -> None:
        """Mark this handle as inactive. Does NOT stop the distro."""
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
                cwd=self._default_cwd,
                timeout=timeout_ms / 1000,
            )
        except VMError as e:
            raise CLIError(str(e)) from e

    async def upload(self, src: str, dst: str) -> None:
        """Transfer a file from the host to the WSL session."""
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
        """Transfer a file from the WSL session to the host.

        Files owned by the session user may not be readable via UNC
        paths.  Work around this by sudo-copying to a world-readable
        temp location first, mirroring the strategy used by :meth:`upload`.
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
# MERGE NOTE: This class is structurally identical to ``vm.LocalVM``.
# The only concrete difference is the platform guard and the backend
# import (``WslVM`` vs ``LimaVM``).  All session-management logic
# (mount resolution, user creation, petname generation, etc.) is
# backend-agnostic and can be shared.
# ------------------------------------------------------------------


class LocalVM:
    """A shared WSL2 distro that hands out isolated session computers.

    Mount state lives in ``mounts.json`` (the single source of truth).
    All mount/unmount operations read from and write to that config
    directly — no in-memory mount tracking.

    Parameters:
        instance: WSL distribution name.
    """

    def __init__(self, *, instance: str = "hexagent") -> None:
        """Initialize with a WSL distribution name.

        MERGE NOTE: When unifying with ``vm.py``, this is the platform
        dispatch point.  Replace the ``if`` guard with:

        .. code-block:: python

            if sys.platform == "darwin":
                from ._lima import LimaVM as _Backend

                self._vm = _Backend(instance=instance)
            elif sys.platform == "win32":
                from ._wsl import WslVM as _Backend

                self._vm = _Backend(instance=instance)
            else:
                raise UnsupportedPlatformError(...)
        """
        # Platform check is delegated to WslVM.__init__(), which raises
        # UnsupportedPlatformError on non-Windows platforms.
        from hexagent.computer.local._wsl import WslVM as _WslVM

        self._vm: WslVM = _WslVM(instance=instance)
        self._instance = instance
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Ensure the distro is running and session mounts are applied.

        WSL bind mounts are ephemeral; they are often absent if the distro
        was started outside LocalVM (for example during setup/build flows).
        Always delegate to ``WslVM.start()`` so it can re-apply mounts from
        ``mounts.json`` even when status is already Running.
        """
        await self._vm.start()

    async def stop(self) -> None:
        """Stop the distro. Idempotent."""
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
        """Add one or more mounts to the distro.

        Idempotent: mounts already present in mounts.json (same host path,
        guest path, and writable flag) are silently skipped.

        Args:
            mounts: A single mount or list of mounts to add.
            session: Target session name. ``None`` = system scope (``/mnt/``).
            defer: If ``True``, update mounts.json but skip the distro restart.
                Call :meth:`apply` later to apply all deferred changes in
                a single restart.

        Raises:
            ValueError: Invalid mount source.
            VMMountConflictError: Guest path conflict with different config.
            VMError: Session does not exist on the distro.
        """
        mount_list = [mounts] if isinstance(mounts, Mount) else list(mounts)
        if not mount_list:
            return

        self._validate_mounts(mount_list)

        # Validate session user exists on the distro.
        if session is not None:
            result = await self._vm.shell(f"id -u {shlex.quote(session)}")
            if result.exit_code != 0:
                msg = f"Session '{session}' does not exist on the distro"
                raise VMError(msg)

        scope = "session" if session is not None else "system"
        resolved_new = [self._resolve_mount(m, scope=scope, session_name=session) for m in mount_list]

        # Within-batch conflict check.
        self._check_conflicts(resolved_new, scope_label=session or "system")

        async with self._lock:
            existing = self._vm.read_mounts()
            existing_set = _mount_set(existing)

            truly_new = [r for r in resolved_new if (r.host_path, r.guest_path, r.writable) not in existing_set]
            if not truly_new:
                # Config may already contain the mount while the live bind mount
                # was lost (for example after external WSL restart). Verify and
                # self-heal by restoring only the missing live bind mount.
                for r in resolved_new:
                    probe = await self._vm.shell(f"findmnt -n {shlex.quote(r.guest_path)}")
                    if probe.exit_code != 0:
                        from hexagent.computer.local._wsl import _session_user_from_guest_mount_path, _win_path_to_wsl

                        wsl_host = _win_path_to_wsl(r.host_path)
                        qguest = shlex.quote(r.guest_path)
                        qhost = shlex.quote(wsl_host)
                        cmd = f"mkdir -p {qguest} && mount --bind {qhost} {qguest}"
                        if not r.writable:
                            cmd += f" && mount -o remount,ro,bind {qguest}"
                        remount = await self._vm.shell(cmd, user="root")
                        if remount.exit_code != 0:
                            msg = f"Failed to self-heal mount '{r.guest_path}': {remount.stderr or remount.stdout}"
                            raise VMError(msg)

                        sess = _session_user_from_guest_mount_path(r.guest_path)
                        skip_chown = os.environ.get("OPENAGENT_WSL_SKIP_SESSION_MOUNT_CHOWN", "").strip().lower() in (
                            "1",
                            "true",
                            "yes",
                        )
                        if r.writable and sess is not None and not skip_chown:
                            quser = shlex.quote(sess)
                            await self._vm.shell(f"chown -R {quser}:{quser} {qguest}", user="root")

                        verify = await self._vm.shell(f"findmnt -n {qguest}", user="root")
                        if verify.exit_code != 0 or not (verify.stdout or "").strip():
                            msg = f"Mount self-heal verification failed for '{r.guest_path}'"
                            raise VMError(msg)
                return

            existing_guests = {r.guest_path for r in existing}
            for r in truly_new:
                if r.guest_path in existing_guests:
                    msg = f"Mount conflict: guest path '{r.guest_path}' is already in use"
                    raise VMMountConflictError(msg)

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

        Idempotent: targets not found in mounts.json are silently skipped.

        Args:
            targets: A single target or list of targets to remove.
            session: Scope. ``None`` = system.
            defer: If ``True``, update mounts.json but skip the distro restart.
        """
        target_list = [targets] if isinstance(targets, str) else list(targets)
        if not target_list:
            return

        scope = "session" if session is not None else "system"
        guest_paths_to_remove = {self._target_to_guest(t, scope=scope, session_name=session) for t in target_list}

        async with self._lock:
            existing = self._vm.read_mounts()
            remaining = [m for m in existing if m.guest_path not in guest_paths_to_remove]

            if len(remaining) == len(existing):
                return

            if defer:
                self._vm.write_mounts(remaining)
            else:
                await self._vm.apply_mounts(remaining)

    def list_mounts(self, *, session: str | None = None) -> list[ResolvedMount]:
        """Return mounts from mounts.json (the source of truth).

        Args:
            session: If given, filter to that session's mounts only.
                ``None`` returns all mounts.

        Returns:
            Resolved mounts currently configured in the distro.
        """
        all_mounts = self._vm.read_mounts()
        if session is not None:
            prefix = f"/sessions/{session}/"
            return [m for m in all_mounts if m.guest_path.startswith(prefix)]
        return all_mounts

    async def apply(self) -> None:
        """Apply deferred mount/unmount changes by restarting the distro.

        Raises:
            VMError: If the WSL distro does not exist.
        """
        async with self._lock:
            status = await self._vm.status()
            if status is None:
                msg = f"WSL distro '{self._instance}' does not exist"
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
            result = await self._vm.shell(f"id -u {shlex.quote(resume)}")
            if result.exit_code != 0:
                msg = f"Session '{resume}' does not exist on the distro"
                raise VMError(msg)
            name = resume
        else:
            name = await self._generate_unique_name()
            await self._create_user(name)

            if mounts:
                try:
                    await self.mount(mounts, session=name)
                except Exception:
                    await self._vm.shell(f"sudo userdel -r {shlex.quote(name)}")
                    raise

        # Keep cowork commands inside the session home by default. Without an
        # explicit cwd, WSL may inherit a host-side working directory
        # (e.g. /mnt/c/Windows/System32), which is often not writable.
        default_cwd = f"/sessions/{name}"
        return _VMSessionComputer(vm=self._vm, session_name=name, default_cwd=default_cwd)

    async def destroy(self, name: str) -> None:
        """Delete a session user and its mounts.

        Args:
            name: Session name to destroy.
        """
        if await self._vm.status() != "Running":
            await self.start()

        await self._vm.shell(f"sudo userdel -r {shlex.quote(name)}")

        async with self._lock:
            existing = self._vm.read_mounts()
            prefix = f"/sessions/{name}/"
            remaining = [m for m in existing if not m.guest_path.startswith(prefix)]

            if len(remaining) != len(existing):
                await self._vm.apply_mounts(remaining)

    async def list_sessions(self) -> list[str]:
        """List active sessions on the distro."""
        if await self._vm.status() != "Running":
            msg = "WSL distro is not running — call start() first"
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
        r"""Validate mount sources exist and are directories.

        MERGE NOTE: This works identically on Windows and macOS because
        ``pathlib.Path`` handles platform-native paths automatically
        (e.g., ``C:\\Users\\...`` on Windows, ``/Users/...`` on macOS).
        """
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
        seen: dict[str, str] = {}
        for m in resolved:
            if m.guest_path in seen:
                msg = f"Mount conflict in {scope_label}: '{m.host_path}' and '{seen[m.guest_path]}' both target '{m.guest_path}'"
                raise VMMountConflictError(msg)
            seen[m.guest_path] = m.host_path

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _generate_unique_name(self, max_attempts: int = 5) -> str:
        """Generate a unique petname not colliding with existing distro users."""
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
        sudo_probe = await self._vm.shell("command -v sudo >/dev/null 2>&1")
        sudo_prefix = "sudo " if sudo_probe.exit_code == 0 else ""

        create_cmd = (
            f"{sudo_prefix}useradd -m -d {qhome} -s /bin/bash "
            f"--no-log-init -K SUB_UID_COUNT=0 -K SUB_GID_COUNT=0 {qname}"
        )
        result = await self._vm.shell(create_cmd)
        if result.exit_code != 0:
            # Some Ubuntu/WSL images reject useradd with SUB_UID/GID_COUNT=0.
            # Retry without those overrides for compatibility. We retry
            # regardless of locale-specific stderr text.
            fallback_cmd = (
                f"{sudo_prefix}useradd -m -d {qhome} -s /bin/bash "
                f"--no-log-init {qname}"
            )
            result = await self._vm.shell(fallback_cmd)
        if result.exit_code != 0:
            msg = f"Failed to create session user '{name}': {result.stderr}"
            raise VMError(msg)

        all_dirs = " ".join(shlex.quote(f"{home}/{d}") for d in SESSION_DIRS)
        writable = f"{shlex.quote(f'{home}/{SESSION_TMP_DIR}')} {shlex.quote(f'{home}/{SESSION_OUTPUTS_DIR}')}"
        result = await self._vm.shell(f"{sudo_prefix}mkdir -p {all_dirs} && {sudo_prefix}chown {qname} {writable}")
        if result.exit_code != 0:
            msg = f"Failed to create session directories for '{name}': {result.stderr}"
            raise VMError(msg)
