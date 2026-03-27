r"""WSL2 distribution management via wsl.exe.

Manages the lifecycle of a WSL2 distribution (import, start, stop, shell).
This is infrastructure — not a Computer implementation. Session management
lives in ``LocalVM`` (see ``vm_win.py``).

Mirrors the interface of ``_lima.py`` (LimaVM) so that ``vm_win.py`` can
use identical session-management logic. The key differences from Lima:

- **Shell**: WSL has native ``-u <user>`` support (no sudo wrapping).
- **Mounts**: No built-in mount config; uses ``mounts.json`` + ``mount --bind``.
- **File transfer**: Uses UNC paths (``\\\\wsl.localhost\\<distro>\\...``)
  instead of ``limactl copy``.
- **Lifecycle**: WSL distros auto-start on any ``wsl -d`` command.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import shlex
import shutil
import sys
import time
from pathlib import Path

from hexagent.computer.base import ExecutionMetadata
from hexagent.computer.local._types import ResolvedMount
from hexagent.exceptions import MissingDependencyError, UnsupportedPlatformError, WslError
from hexagent.types import CLIResult

logger = logging.getLogger(__name__)

# UNC path prefixes for accessing WSL filesystem from Windows.
# Modern Windows 11 uses ``wsl.localhost``; older builds use ``wsl$``.
_UNC_PREFIXES = (r"\\wsl.localhost", r"\\wsl$")

# Capture at module level so mypy does not narrow on ``sys.platform``
# (which would make everything after the platform guard "unreachable"
# when type-checking on macOS/Linux).
_PLATFORM = sys.platform


def _resolve_wsl_exe() -> str | None:
    """Return a usable ``wsl.exe`` path.

    Some hosts (notably Electron-spawned backends) omit ``System32`` from
    ``PATH``, so ``shutil.which`` fails even though WSL is installed.
    """
    w = shutil.which("wsl.exe") or shutil.which("wsl")
    if w:
        return w
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
    if not system_root:
        system_root = r"C:\Windows"
    candidate = Path(system_root) / "System32" / "wsl.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _stable_host_cwd() -> str:
    """Return a safe Windows cwd for launching ``wsl.exe``.

    WSL tries to translate the parent process cwd into Linux path on every
    invocation. If that cwd is a stale UNC/session path, startup prints
    ``CreateProcessCommon: ... chdir(...) failed`` and commands may run in an
    unexpected context. Force a stable host cwd to avoid inheriting stale
    per-session paths.
    """
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR") or r"C:\Windows"
    # ``wsl.exe`` exists under System32 on supported hosts; use that directory
    # as a stable cwd if available, otherwise fall back to the process cwd.
    safe_dir = Path(system_root) / "System32"
    if safe_dir.is_dir():
        return str(safe_dir)
    return str(Path.cwd())


def _ensure_proactor_event_loop() -> None:
    """Switch to ``ProactorEventLoop`` if not already active.

    ``asyncio.create_subprocess_exec`` requires ``ProactorEventLoop`` on
    Windows.  Some frameworks (e.g. uvicorn) force ``SelectorEventLoop``,
    which silently breaks subprocess support.  This function sets the
    ``WindowsProactorEventLoopPolicy`` so that all future event loops
    use the correct implementation.

    No-op on non-Windows platforms (guard is in the caller).
    """
    current_policy = asyncio.get_event_loop_policy()  # type: ignore[deprecated,unused-ignore]
    # WindowsProactorEventLoopPolicy is only available on Windows;
    # access it via getattr to keep the module importable on macOS/Linux.
    proactor_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor_cls is not None and not isinstance(current_policy, proactor_cls):
        asyncio.set_event_loop_policy(proactor_cls())  # type: ignore[deprecated,unused-ignore]


def _check_wsl_prerequisites() -> None:
    """Verify we are on Windows with WSL available.

    Also ensures the ``ProactorEventLoop`` policy is active.  On Windows,
    uvicorn (and some other frameworks) force ``SelectorEventLoop``, which
    does **not** support ``asyncio.create_subprocess_exec``.  Setting the
    policy here keeps the fix self-contained — every code path that
    instantiates ``WslVM`` gets it automatically, regardless of the
    application entry point.

    Raises:
        UnsupportedPlatformError: If not on Windows.
        MissingDependencyError: If ``wsl.exe`` is not found.
    """
    if _PLATFORM != "win32":
        msg = f"WSL is a Windows subsystem — it cannot run on {_PLATFORM}"
        raise UnsupportedPlatformError(msg)
    if _resolve_wsl_exe() is None:
        msg = "wsl.exe not found. Install WSL2: https://learn.microsoft.com/windows/wsl/install"
        raise MissingDependencyError(msg)

    # Ensure ProactorEventLoop is used so create_subprocess_exec works.
    # SelectorEventLoop (uvicorn's default on Windows) does not support it.
    _ensure_proactor_event_loop()


class WslVM:
    """Manages a single WSL2 distribution instance.

    Parameters:
        instance: WSL distribution name.
    """

    def __init__(self, instance: str) -> None:
        _check_wsl_prerequisites()
        wsl_exe = _resolve_wsl_exe()
        assert wsl_exe is not None  # noqa: S101
        self._wsl_exe = wsl_exe
        self._instance = instance
        self._unc_prefix: str | None = None  # cached after first successful probe

    @property
    def instance(self) -> str:
        """Read-only WSL distribution name."""
        return self._instance

    @property
    def _config_dir(self) -> Path:
        """Config directory for this instance."""
        data_dir = os.environ.get("HEXAGENT_DATA_DIR")
        base = Path(data_dir) if data_dir else Path.home() / ".hexagent"
        return base / "wsl" / self._instance

    @property
    def _config_path(self) -> Path:
        """Path to ``mounts.json`` for this instance."""
        return self._config_dir / "mounts.json"

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    async def status(self) -> str | None:
        """Return the distribution status string, or ``None`` if it doesn't exist.

        Returns:
            ``"Running"``, ``"Stopped"``, or ``None``.

        Raises:
            WslError: If the distribution exists but is WSL version 1.
        """
        proc = await asyncio.create_subprocess_exec(
            self._wsl_exe,
            "--list",
            "--verbose",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, _ = await proc.communicate()

        if proc.returncode != 0:
            return None

        entries = _parse_status_output(stdout_bytes)
        for entry in entries:
            if entry["name"].lower() == self._instance.lower():
                if entry["version"] != "2":
                    msg = (
                        f"WSL distro '{self._instance}' is version {entry['version']}; "
                        "WSL2 is required. Convert with: wsl --set-version "
                        f"{self._instance} 2"
                    )
                    raise WslError(msg)
                return entry["state"]

        return None

    # ------------------------------------------------------------------
    # Mount inspection
    # ------------------------------------------------------------------

    def read_mounts(self) -> list[ResolvedMount]:
        """Read the current mount configuration from ``mounts.json``.

        Returns:
            List of resolved mounts currently configured.
            Empty list if the file doesn't exist or has no mounts.
        """
        if not self._config_path.exists():
            return []

        with self._config_path.open("r", encoding="utf-8") as f:
            data: dict[str, object] = json.load(f)

        raw_mounts = data.get("mounts", [])
        if not isinstance(raw_mounts, list):
            return []

        result: list[ResolvedMount] = []
        for entry in raw_mounts:
            if not isinstance(entry, dict):
                continue
            host_path = entry.get("host_path")
            guest_path = entry.get("guest_path")
            if host_path is None or guest_path is None:
                continue
            result.append(
                ResolvedMount(
                    host_path=str(host_path),
                    guest_path=str(guest_path),
                    writable=bool(entry.get("writable", False)),
                )
            )
        return result

    def write_mounts(self, mounts: list[ResolvedMount]) -> None:
        """Write mount configuration to ``mounts.json``.

        The change takes effect on the next distro restart (via
        ``apply_mounts`` or ``start``).

        Creates the config directory if missing. This can happen when a distro
        was installed outside ``build()`` (for example via setup migration or
        manual WSL import) and cowork mounts are configured later.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)

        entries = [
            {
                "host_path": m.host_path,
                "guest_path": m.guest_path,
                "writable": m.writable,
            }
            for m in mounts
        ]

        with self._config_path.open("w", encoding="utf-8") as f:
            json.dump({"mounts": entries}, f, indent=2)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def build(self, tarball_path: Path | str) -> None:
        """Import a new WSL2 distribution from a rootfs tarball.

        Blocks until the import completes.

        Raises:
            WslError: If the distribution already exists.
        """
        current = await self.status()
        if current is not None:
            msg = f"WSL distro '{self._instance}' already exists (status: {current})"
            raise WslError(msg)

        disk_dir = self._config_dir / "disk"
        disk_dir.mkdir(parents=True, exist_ok=True)

        await self._run_wsl(
            self._wsl_exe,
            "--import",
            self._instance,
            str(disk_dir),
            str(tarball_path),
            timeout=600,
        )

        # Initialize empty mount config.
        with self._config_path.open("w", encoding="utf-8") as f:
            json.dump({"mounts": []}, f, indent=2)

        # Create /sessions/ directory inside the distro.
        await self.shell("mkdir -p /sessions", user="root")

    async def start(self) -> None:
        """Start the WSL distribution. Idempotent.

        Also re-applies bind mounts from ``mounts.json`` (since WSL bind
        mounts are ephemeral and lost on terminate).

        Raises:
            WslError: If the distribution doesn't exist.
        """
        current = await self.status()

        if current is None:
            msg = f"WSL distro '{self._instance}' does not exist. Create it first with build()."
            raise WslError(msg)

        if current != "Running":
            # Trigger start by running a trivial command.
            # Some Windows hosts occasionally return a transient -1/4294967295
            # from wsl.exe during startup even though a subsequent attempt works.
            for attempt in range(2):
                try:
                    await self._run_wsl(
                        self._wsl_exe,
                        "-d",
                        self._instance,
                        "--",
                        "echo",
                        "ok",
                        timeout=120,
                    )
                    break
                except WslError as exc:
                    text = str(exc).lower()
                    transient = "exit 4294967295" in text or "exit -1" in text
                    if transient and attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    raise

        await self._apply_bind_mounts()

    async def apply_mounts(self, mounts: list[ResolvedMount]) -> None:
        """Apply mount configuration to the distribution.

        Writes the config, terminates the distro (clearing old bind
        mounts), restarts, and applies new bind mounts.

        Args:
            mounts: Complete list of resolved mounts. Replaces all
                existing mounts in ``mounts.json``.

        Raises:
            WslError: If the distribution does not exist or start fails.
        """
        current = await self.status()
        if current is None:
            msg = f"WSL distro '{self._instance}' does not exist"
            raise WslError(msg)

        self.write_mounts(mounts)

        if current == "Running":
            await self.stop()

        await self.start()

    async def stop(self) -> None:
        """Terminate the WSL distribution.

        No-op if already stopped.

        Raises:
            WslError: If the terminate command fails.
        """
        current = await self.status()
        if current is None or current != "Running":
            return

        await self._run_wsl(
            self._wsl_exe,
            "--terminate",
            self._instance,
            timeout=60,
        )

    async def delete(self) -> None:
        """Unregister the WSL distribution and clean up config (best-effort)."""
        with contextlib.suppress(WslError):
            await self._run_wsl(
                self._wsl_exe,
                "--unregister",
                self._instance,
            )
        # Clean up local config directory.
        with contextlib.suppress(OSError):
            if self._config_dir.exists():
                shutil.rmtree(self._config_dir)

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
    ) -> CLIResult:
        """Execute a command inside the WSL distribution.

        Parameters:
            command: Shell command to run.
            user: If set, run as this Linux user via ``wsl -u``.
            cwd: Working directory inside the distribution.
            timeout: Timeout in **seconds**. ``None`` means wait indefinitely.

        Returns:
            CLIResult with stdout, stderr, exit_code, and metadata.

        Raises:
            WslError: On timeout or subprocess failure.
        """
        inner = f"cd {shlex.quote(cwd)} && {command}" if cwd is not None else command

        exec_args: list[str] = [self._wsl_exe, "-d", self._instance]
        if user is not None:
            exec_args += ["-u", user]
        exec_args += ["--", "bash"]
        if user is not None:
            # Login shell for user sessions so that profile/env are loaded.
            exec_args.append("-l")
        exec_args += ["-c", inner]

        start_time = time.monotonic()

        process = await asyncio.create_subprocess_exec(
            *exec_args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_stable_host_cwd(),
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            process.kill()
            await process.wait()
            msg = f"timed out after {timeout}s"
            raise WslError(msg) from None

        stdout = stdout_bytes.decode("utf-8", errors="replace").removesuffix("\n")
        stderr = stderr_bytes.decode("utf-8", errors="replace").removesuffix("\n")

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
        """Copy a file between host and guest via UNC paths.

        Args:
            src: Source path (host path if host_to_guest, else guest path).
            dst: Destination path (guest path if host_to_guest, else host path).
            host_to_guest: Direction of the copy.

        Raises:
            WslError: If the copy fails.
        """
        unc_prefix = await self._resolve_unc_prefix()

        try:
            if host_to_guest:
                unc_dst = f"{unc_prefix}\\{self._instance}{dst.replace('/', os.sep)}"
                # Ensure parent directory exists on guest side.
                unc_parent = str(Path(unc_dst).parent)
                await asyncio.to_thread(os.makedirs, unc_parent, exist_ok=True)
                await asyncio.to_thread(shutil.copy2, src, unc_dst)
            else:
                unc_src = f"{unc_prefix}\\{self._instance}{src.replace('/', os.sep)}"
                await asyncio.to_thread(shutil.copy2, unc_src, dst)
        except OSError as e:
            msg = f"File copy failed: {e}"
            raise WslError(msg) from e

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _run_wsl(self, *cmd: str, timeout: float = 300) -> str:  # noqa: ASYNC109
        """Run a wsl.exe command to completion.

        Args:
            *cmd: Command and arguments.
            timeout: Maximum seconds to wait. Defaults to 5 minutes.

        Returns:
            Decoded stdout.

        Raises:
            WslError: On non-zero exit code or timeout.
        """
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_stable_host_cwd(),
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            msg = f"wsl.exe timed out after {timeout}s: {' '.join(cmd[:3])}"
            raise WslError(msg) from None

        if proc.returncode != 0:
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            msg = f"wsl.exe failed (exit {proc.returncode}): {stderr}"
            raise WslError(msg)

        return stdout_bytes.decode("utf-8", errors="replace")

    async def _apply_bind_mounts(self) -> None:
        """Apply all bind mounts from ``mounts.json`` inside the distro.

        Idempotent: skips mounts that are already active (detected via
        ``mountpoint -q``).
        """
        mounts = self.read_mounts()
        if not mounts:
            return

        logger.debug("WSL applying %d bind mount(s) from mounts.json", len(mounts))

        for m in mounts:
            wsl_host = _win_path_to_wsl(m.host_path)
            qguest = shlex.quote(m.guest_path)
            qhost = shlex.quote(wsl_host)

            # Skip if already mounted.
            check = await self.shell(f"mountpoint -q {qguest}", user="root")
            if check.exit_code == 0:
                logger.info(
                    "WSL bind-mount already active: guest=%s wsl_source=%s host_win=%s",
                    m.guest_path,
                    wsl_host,
                    m.host_path,
                )
                continue

            cmd = f"mkdir -p {qguest} && mount --bind {qhost} {qguest}"
            if not m.writable:
                cmd += f" && mount -o remount,ro,bind {qguest}"

            result = await self.shell(cmd, user="root")
            if result.exit_code != 0:
                msg = f"Failed to bind-mount {m.host_path} → {m.guest_path}: {result.stderr}"
                raise WslError(msg)

            # Cowork mounts bind a DrvFs path (/mnt/<drive>/...) into /sessions/<user>/mnt/....
            # DrvFs often presents files as root:root with mode 755 to Linux UIDs that are not
            # the WSL default user, so session users see a read-only directory even though
            # Windows ACLs allow writes. chown maps ownership to the session Linux user so
            # mkdir/Write behave consistently.
            sess = _session_user_from_guest_mount_path(m.guest_path)
            skip_chown = os.environ.get("OPENAGENT_WSL_SKIP_SESSION_MOUNT_CHOWN", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
            if m.writable and sess is not None and not skip_chown:
                quser = shlex.quote(sess)
                own = await self.shell(f"chown -R {quser}:{quser} {qguest}", user="root")
                if own.exit_code != 0:
                    logger.warning(
                        "WSL post-bind chown failed (session=%s guest=%s): %s",
                        sess,
                        m.guest_path,
                        (own.stderr or own.stdout or "").strip() or "(empty)",
                    )

            # Post-verify so logs show whether the guest path is really a mount (debug empty ls issues).
            verify = await self.shell(f"findmnt -n {qguest}", user="root")
            if verify.exit_code == 0 and (verify.stdout or "").strip():
                logger.info(
                    "WSL bind-mount applied+verified: guest=%s host_win=%s findmnt=%s",
                    m.guest_path,
                    m.host_path,
                    verify.stdout.strip().replace("\n", " | "),
                )
            else:
                logger.warning(
                    "WSL bind-mount mount(8) succeeded but findmnt could not confirm guest=%s "
                    "(host_win=%s, wsl_source=%s, findmnt_exit=%s, findmnt_stderr=%s)",
                    m.guest_path,
                    m.host_path,
                    wsl_host,
                    verify.exit_code,
                    (verify.stderr or "").strip() or "(empty)",
                )

    async def _resolve_unc_prefix(self) -> str:
        r"""Resolve and cache the working UNC prefix for this system.

        Tries ``\\\\wsl.localhost`` first, falls back to ``\\\\wsl$``.
        """
        if self._unc_prefix is not None:
            return self._unc_prefix

        for prefix in _UNC_PREFIXES:
            test_path = f"{prefix}\\{self._instance}"
            exists = await asyncio.to_thread(os.path.isdir, test_path)
            if exists:
                self._unc_prefix = prefix
                return prefix

        # Default to modern prefix if probing fails (distro may not be running).
        self._unc_prefix = _UNC_PREFIXES[0]
        return self._unc_prefix

    @staticmethod
    def _build_mount_set_arg(mounts: list[ResolvedMount]) -> str:
        """Build a JSON representation of the mount list.

        Provided for interface parity with LimaVM. Not used directly
        by WSL, but useful for debugging and logging.
        """
        entries = [
            {
                "host_path": m.host_path,
                "guest_path": m.guest_path,
                "writable": m.writable,
            }
            for m in mounts
        ]
        return json.dumps(entries)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _win_path_to_wsl(win_path: str) -> str:
    r"""Convert a Windows path to its WSL ``/mnt/`` equivalent.

    Examples:
        >>> _win_path_to_wsl(r"C:\\Users\\foo")
        '/mnt/c/Users/foo'
        >>> _win_path_to_wsl("D:/data")
        '/mnt/d/data'

    Raises:
        WslError: For UNC paths, relative paths, or unrecognisable formats.
    """
    # Reject UNC paths.
    if win_path.startswith(("\\\\", "//")):
        msg = f"UNC paths are not supported for WSL mounts: {win_path}"
        raise WslError(msg)

    # Normalise forward slashes.
    normalised = win_path.replace("\\", "/")

    # Match drive-letter paths: C:/... or C:...
    match = re.match(r"^([A-Za-z]):(.*)", normalised)
    if not match:
        msg = f"Cannot convert to WSL path (expected drive letter): {win_path}"
        raise WslError(msg)

    drive = match.group(1).lower()
    rest = match.group(2)

    # Ensure rest starts with /.
    if not rest.startswith("/"):
        rest = "/" + rest

    return f"/mnt/{drive}{rest}"


def _session_user_from_guest_mount_path(guest_path: str) -> str | None:
    """Return the cowork session Linux username if *guest_path* is under ``/sessions/<user>/``.

    Session-scoped mounts resolve to ``/sessions/<petname>/mnt/...``; the first path component
    after ``sessions`` matches the Linux account created for that sandbox session.
    """
    parts = guest_path.split("/")
    if len(parts) >= 3 and parts[1] == "sessions" and parts[2]:  # noqa: PLR2004
        return parts[2]
    return None


def _parse_status_output(stdout: bytes) -> list[dict[str, str]]:
    """Parse the output of ``wsl --list --verbose``.

    Handles both UTF-16-LE (common on Windows 10/11) and UTF-8 encodings.

    Returns:
        List of dicts with keys ``name``, ``state``, ``version``.
    """
    # Detect encoding: UTF-16-LE typically starts with BOM \xff\xfe.
    # Some Windows builds also use UTF-16-LE without BOM but embed NUL
    # bytes (every other byte is 0x00 for ASCII content).
    if stdout[:2] == b"\xff\xfe":
        text = stdout.decode("utf-16-le", errors="replace")
    elif b"\x00" in stdout:
        # NUL bytes in the raw data strongly suggest UTF-16 encoding.
        text = stdout.decode("utf-16-le", errors="replace")
    else:
        text = stdout.decode("utf-8", errors="replace")

    # Strip NUL bytes that may appear in UTF-16-LE decoded output.
    text = text.replace("\x00", "")

    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Skip header line (contains "NAME" and "STATE").
        if "NAME" in stripped.upper() and "STATE" in stripped.upper():
            continue

        # Strip leading * (marks default distro).
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()

        # Split by whitespace: <name> <state> <version>
        parts = stripped.split()
        if len(parts) >= 3:  # noqa: PLR2004
            entries.append(
                {
                    "name": parts[0],
                    "state": parts[1],
                    "version": parts[2],
                }
            )

    return entries
