"""Setup endpoints — VM backend detection, installation, build & provisioning.

Currently supports Lima (macOS). WSL (Windows) support planned.
Platform dispatch happens here; the frontend only sees generic
``/api/setup/vm`` endpoints and a ``backend`` field in the response.
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import os
import platform
import re
import shutil
import subprocess as _sp
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from openagent_api.paths import deps_dir, vm_lima_dir, vm_setup_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/setup", tags=["setup"])

# ---------------------------------------------------------------------------
# Lima (macOS)
# ---------------------------------------------------------------------------

_LIMA_FALLBACK_VERSION = "2.1.0"
_LIMA_MAJOR = 2  # Accept v2.x.x releases only

_LIMA_RELEASES_API = "https://api.github.com/repos/lima-vm/lima/releases"
_LIMA_RELEASE_URL = (
    "https://github.com/lima-vm/lima/releases/download"
    "/v{version}/lima-{version}-{os}-{arch}.tar.gz"
)


def _lima_dir() -> Path:
    return deps_dir() / "lima"


def _lima_bin() -> Path:
    return _lima_dir() / "bin" / "limactl"


def _resolve_arch() -> str:
    """Map platform.machine() to Lima release asset arch names.

    Lima release naming differs by OS:
      - macOS (Darwin): ``arm64``, ``x86_64``
      - Linux:          ``aarch64``, ``x86_64``
    Since we only install Lima on macOS, we use macOS naming.
    """
    m = platform.machine().lower()
    if m in ("arm64", "aarch64"):
        return "arm64"
    if m in ("x86_64", "amd64"):
        return "x86_64"
    return m


async def _check_url_exists(url: str) -> bool:
    """Return True if *url* is downloadable (fetch first byte)."""
    proc = await asyncio.create_subprocess_exec(
        "curl", "-fsSL", "-r", "0-0", "-o", "/dev/null",
        "-w", "%{http_code}", url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
    except asyncio.TimeoutError:
        return False
    code = (stdout or b"").decode().strip()
    return code.startswith("2")


async def _resolve_lima_version() -> str:
    """Fetch the latest *downloadable* stable Lima v{_LIMA_MAJOR}.x version.

    Lists releases from the GitHub API, then verifies the tarball URL is
    reachable (new releases can 404 while CDN propagation is in progress).
    Falls back to ``_LIMA_FALLBACK_VERSION`` if nothing works.
    """
    candidates: list[str] = []
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-fsSL", "--retry", "2", "--retry-delay", "2",
            "-H", "Accept: application/vnd.github+json",
            _LIMA_RELEASES_API,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0 and stdout:
            releases = json.loads(stdout)
            tag_re = re.compile(rf"^v({_LIMA_MAJOR}\.\d+\.\d+)$")
            for rel in releases:
                if rel.get("draft") or rel.get("prerelease"):
                    continue
                m = tag_re.match(rel.get("tag_name", ""))
                if m:
                    candidates.append(m.group(1))
    except Exception:
        logger.debug("Failed to list Lima releases", exc_info=True)

    # Ensure the fallback is always tried last
    if _LIMA_FALLBACK_VERSION not in candidates:
        candidates.append(_LIMA_FALLBACK_VERSION)

    # Pick the first candidate whose tarball is actually downloadable
    for version in candidates:
        url = _lima_tarball_url(version)
        if await _check_url_exists(url):
            return version

    # Nothing reachable — return newest anyway, let the download fail
    # with a clear error rather than silently picking something wrong.
    return candidates[0]


def _lima_tarball_url(version: str) -> str:
    """Build the GitHub release tarball URL for this platform."""
    return _LIMA_RELEASE_URL.format(
        version=version,
        os="Darwin",
        arch=_resolve_arch(),
    )


def _ensure_managed_lima_on_path() -> None:
    """Prepend the managed Lima bin dir to PATH if it exists."""
    if _lima_bin().is_file():
        bin_dir = str(_lima_bin().parent)
        path = os.environ.get("PATH", "")
        if bin_dir not in path.split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + path
            logger.info("Added managed Lima to PATH: %s", bin_dir)


def _lima_status() -> dict[str, object]:
    """Check Lima installation status."""
    limactl = shutil.which("limactl")
    if limactl:
        return {"installed": True, "path": limactl, "managed": str(limactl) == str(_lima_bin())}
    return {"installed": False, "path": None, "managed": False}


async def _install_lima_stream():
    """SSE generator that downloads and installs Lima."""
    def sse(event: str, data: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    yield sse("progress", {"step": "resolving", "message": "Resolving latest Lima version..."})

    version = await _resolve_lima_version()
    yield sse("progress", {"step": "downloading", "message": f"Downloading Lima v{version}..."})

    tmp_dir = tempfile.mkdtemp(prefix="openagent_lima_")
    tarball_path = os.path.join(tmp_dir, "lima.tar.gz")

    try:
        url = _lima_tarball_url(version)
        proc = await asyncio.create_subprocess_exec(
            "curl", "-fSL", "--progress-bar", "-o", tarball_path, url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            yield sse("error", {"message": "Download timed out"})
            return

        if proc.returncode != 0:
            err = (stderr or b"").decode(errors="replace").strip()
            yield sse("error", {"message": f"Download failed: {err}"})
            return

        yield sse("progress", {"step": "extracting", "message": "Extracting..."})

        _lima_dir().mkdir(parents=True, exist_ok=True)

        def _extract() -> None:
            with tarfile.open(tarball_path, "r:gz") as tf:
                tf.extractall(path=str(_lima_dir()))  # noqa: S202

        await asyncio.to_thread(_extract)

        # Make binaries executable
        bin_dir = _lima_dir() / "bin"
        if bin_dir.is_dir():
            for f in bin_dir.iterdir():
                f.chmod(f.stat().st_mode | 0o755)

        if not _lima_bin().is_file():
            yield sse("error", {"message": "Installation failed: limactl binary not found after extraction"})
            return

        _ensure_managed_lima_on_path()
        yield sse("done", {"message": f"Lima v{version} installed successfully", "path": str(_lima_bin())})

    except Exception as exc:
        logger.exception("Lima installation failed")
        yield sse("error", {"message": str(exc)})
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Platform dispatch
# ---------------------------------------------------------------------------


def ensure_managed_deps_on_path() -> None:
    """Ensure any managed VM backend binaries are on PATH.

    Called once at backend startup.
    """
    if sys.platform == "darwin":
        _ensure_managed_lima_on_path()
    # Future: WSL on Windows needs no PATH manipulation


def _vm_status() -> dict[str, object]:
    """Return platform-aware VM backend status.

    Shape (always present):
        supported: bool
        backend: "lima" | "wsl" | null
        installed: bool

    Plus backend-specific fields (path, managed, reason, etc.).
    """
    if sys.platform == "darwin":
        return {"supported": True, "backend": "lima", **_lima_status()}
    if sys.platform == "win32":
        # Placeholder for WSL support
        return {"supported": True, "backend": "wsl", "installed": False}
    return {"supported": False, "backend": None, "installed": False, "reason": f"No VM backend for {sys.platform}"}


# ---------------------------------------------------------------------------
# Endpoints — generic /vm, frontend doesn't need to know Lima vs WSL
# ---------------------------------------------------------------------------


@router.get("/vm")
async def get_vm_status() -> dict[str, object]:
    """Check whether the VM backend is available.

    Returns ``vm_ready: true`` only when the backend is installed AND
    the VM instance is running — i.e. cowork mode can start sessions
    immediately.
    """
    result = _vm_status()

    # Quick readiness check: installed + instance running?
    vm_ready = False
    instance_status: str | None = None
    if result.get("installed"):
        try:
            instance_status = await _lima_instance_status()
            vm_ready = instance_status == "Running"
        except Exception:
            pass

    result["instance_status"] = instance_status
    result["vm_ready"] = vm_ready
    return result


@router.post("/vm/install")
async def install_vm_backend() -> StreamingResponse:
    """Install the platform-appropriate VM backend.

    Streams SSE progress events (progress, done, error).
    """
    status = _vm_status()

    if not status["supported"]:
        raise HTTPException(status_code=422, detail=status.get("reason", "VM not supported on this platform"))
    if status["installed"]:
        raise HTTPException(status_code=409, detail="VM backend is already installed")

    backend = status["backend"]
    if backend == "lima":
        return StreamingResponse(_install_lima_stream(), media_type="text/event-stream")

    # Future: WSL installation
    raise HTTPException(status_code=501, detail=f"Auto-install not yet supported for {backend}")


# ---------------------------------------------------------------------------
# Process Manager — base class for long-running subprocess operations
# ---------------------------------------------------------------------------
# Decouples subprocess lifecycle from HTTP request lifecycle so that:
#   - Provisioning continues if the SSE connection drops (tab close)
#   - Reconnecting clients replay buffered events + tail new ones
#   - Multiple concurrent viewers are supported
# ---------------------------------------------------------------------------

_LIMA_INSTANCE = "openagent"


def _sse(event: str, data: dict[str, object]) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _lima_shell(cmd: str, *, timeout: float = 60) -> tuple[int, str, str]:
    """Run a command inside the Lima VM and return (exit_code, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "limactl", "shell", _LIMA_INSTANCE, "--", "bash", "-c", cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 1, "", "Timed out"
    return (
        proc.returncode or 0,
        (stdout_b or b"").decode("utf-8", errors="replace"),
        (stderr_b or b"").decode("utf-8", errors="replace"),
    )


async def _lima_instance_status() -> str | None:
    """Return the Lima instance status ('Running', 'Stopped', …) or None."""
    proc = await asyncio.create_subprocess_exec(
        "limactl", "list", "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, _ = await proc.communicate()
    for line in (stdout_b or b"").decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("name") == _LIMA_INSTANCE:
            return entry.get("status")
    return None


class _ProcessManager(abc.ABC):
    """Base class for managing a long-running subprocess with SSE streaming."""

    def __init__(self) -> None:
        self._status: str = "idle"  # idle | running | done | error
        self._error: str | None = None
        self._events: list[str] = []
        self._new_event = asyncio.Event()
        self._process: asyncio.subprocess.Process | None = None
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    # -- Public API --

    async def start(self, **kwargs: object) -> None:
        """Start the operation if not already running. Idempotent."""
        async with self._lock:
            if self._status == "running":
                return
            # Reset state for a fresh run (or retry after error)
            self._status = "running"
            self._error = None
            self._events.clear()
            self._new_event.clear()
            self._task = asyncio.create_task(self._run_wrapper(**kwargs))

    async def stream(self) -> AsyncIterator[str]:
        """Yield SSE frames: replay buffered events then tail new ones."""
        cursor = 0
        while True:
            # Yield any buffered events we haven't sent yet
            while cursor < len(self._events):
                yield self._events[cursor]
                cursor += 1
            # Terminal — stop streaming
            if self._status in ("done", "error"):
                return
            # Wait for the next event
            self._new_event.clear()
            await self._new_event.wait()

    def cancel(self) -> None:
        """Send SIGTERM to the managed subprocess."""
        if self._process and self._process.returncode is None:
            self._process.terminate()

    def status_dict(self) -> dict[str, object]:
        """Non-streaming status snapshot."""
        return {"status": self._status, "error": self._error}

    # -- Internal --

    def _emit(self, event_type: str, data: dict[str, object]) -> None:
        frame = _sse(event_type, data)
        self._events.append(frame)
        self._new_event.set()

    @abc.abstractmethod
    async def _run(self, **kwargs: object) -> None:
        """Subclass implements the actual work here."""

    async def _run_wrapper(self, **kwargs: object) -> None:
        try:
            await self._run(**kwargs)
            if self._status == "running":
                # _run didn't set a terminal status — assume success
                self._status = "done"
        except asyncio.CancelledError:
            self._status = "error"
            self._error = "Cancelled"
            self._emit("error", {"message": "Cancelled"})
        except Exception as exc:
            logger.exception("%s failed", self.__class__.__name__)
            self._status = "error"
            self._error = str(exc)
            self._emit("error", {"message": str(exc)})
        finally:
            self._new_event.set()


# ---------------------------------------------------------------------------
# Build Manager — creates / starts the Lima VM
# ---------------------------------------------------------------------------


class _BuildManager(_ProcessManager):
    """Manages ``limactl start`` to create or boot the VM."""

    async def _run(self, **kwargs: object) -> None:
        instance_status = await _lima_instance_status()

        if instance_status == "Running":
            self._emit("done", {"message": "VM is already running"})
            self._status = "done"
            return

        if instance_status == "Stopped":
            self._emit("progress", {"step": "starting", "message": "Starting existing VM..."})
            proc = await asyncio.create_subprocess_exec(
                "limactl", "start", _LIMA_INSTANCE, "--tty=false",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._process = proc
            await self._stream_stderr(proc)
            await proc.wait()
            if proc.returncode == 0:
                self._emit("done", {"message": "VM started successfully"})
                self._status = "done"
            else:
                self._emit("error", {"message": f"VM start failed (exit {proc.returncode})"})
                self._status = "error"
                self._error = f"exit {proc.returncode}"
            return

        # Instance doesn't exist — full build
        yaml_path = vm_lima_dir() / "openagent.yaml"
        if not yaml_path.is_file():
            self._emit("error", {"message": f"VM config not found: {yaml_path}"})
            self._status = "error"
            self._error = "Config not found"
            return

        self._emit("progress", {"step": "creating", "message": "Creating VM (downloading base image)..."})
        proc = await asyncio.create_subprocess_exec(
            "limactl", "start", f"--name={_LIMA_INSTANCE}", str(yaml_path), "--tty=false",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = proc
        await self._stream_stderr(proc)
        await proc.wait()
        if proc.returncode == 0:
            self._emit("done", {"message": "VM created successfully"})
            self._status = "done"
        else:
            self._emit("error", {"message": f"VM creation failed (exit {proc.returncode})"})
            self._status = "error"
            self._error = f"exit {proc.returncode}"

    async def _stream_stderr(self, proc: asyncio.subprocess.Process) -> None:
        """Read limactl stderr line-by-line and emit progress events."""
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            # Heuristic progress from limactl output
            if "Downloading" in text or "downloading" in text:
                self._emit("progress", {"step": "downloading", "message": text})
            elif "Waiting" in text or "Booting" in text:
                self._emit("progress", {"step": "booting", "message": text})
            elif "READY" in text or "ready" in text:
                self._emit("progress", {"step": "ready", "message": text})
            else:
                self._emit("progress", {"step": "output", "message": text})


# ---------------------------------------------------------------------------
# Provision Manager — runs setup.sh inside the VM
# ---------------------------------------------------------------------------

_SETUP_MARKER_DIR = "/var/lib/openagent/setup"
_SETUP_LOG_DIR = "/var/log/openagent/setup"
_SETUP_VM_DIR = "/tmp/openagent-setup"

# Step IDs that setup.sh discovers (must match filenames in steps/)
_PROVISION_STEPS = [
    ("01_base", "Base prerequisites"),
    ("02_nodejs", "Node.js 22.x"),
    ("03_apt", "System packages"),
    ("04_npm", "NPM global packages"),
    ("05_pip", "Python packages"),
    ("06_playwright", "Playwright browsers"),
    ("07_finalize", "Finalize"),
    ("08_cleanup", "Cleanup"),
]


class _ProvisionManager(_ProcessManager):
    """Manages setup.sh execution inside the Lima VM."""

    async def _run(self, **kwargs: object) -> None:
        force = bool(kwargs.get("force", False))

        # 1. Verify VM is running
        instance_status = await _lima_instance_status()
        if instance_status != "Running":
            self._emit("error", {"message": f"VM is not running (status: {instance_status})"})
            self._status = "error"
            self._error = "VM not running"
            return

        # 2. Copy setup directory into VM
        self._emit("progress", {"step": "copying", "message": "Copying setup files to VM..."})
        setup_dir = vm_setup_dir()
        if not setup_dir.is_dir():
            self._emit("error", {"message": f"Setup directory not found: {setup_dir}"})
            self._status = "error"
            self._error = "Setup dir not found"
            return

        # Tar locally, copy tarball, extract in VM
        with tempfile.TemporaryDirectory(prefix="openagent_setup_") as tmp:
            tar_path = os.path.join(tmp, "setup.tar.gz")
            _sp.run(
                ["tar", "-czf", tar_path, "-C", str(setup_dir.parent), "setup"],
                check=True,
            )
            copy_proc = await asyncio.create_subprocess_exec(
                "limactl", "copy", tar_path, f"{_LIMA_INSTANCE}:/tmp/openagent-setup.tar.gz",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await copy_proc.communicate()
            if copy_proc.returncode != 0:
                self._emit("error", {"message": "Failed to copy setup files to VM"})
                self._status = "error"
                self._error = "Copy failed"
                return

        # Extract in VM
        rc, _, err = await _lima_shell(
            f"sudo rm -rf {_SETUP_VM_DIR} && sudo mkdir -p {_SETUP_VM_DIR} && "
            f"sudo tar -xzf /tmp/openagent-setup.tar.gz -C {_SETUP_VM_DIR} --strip-components=1 && "
            f"rm -f /tmp/openagent-setup.tar.gz",
            timeout=30,
        )
        if rc != 0:
            self._emit("error", {"message": f"Failed to extract setup files in VM: {err}"})
            self._status = "error"
            self._error = "Extract failed"
            return

        # 3. Run setup.sh with progress streaming
        self._emit("progress", {"step": "starting", "message": "Starting provisioning..."})

        cmd = f"sudo bash {_SETUP_VM_DIR}/setup.sh"
        if force:
            cmd += " --force"

        proc = await asyncio.create_subprocess_exec(
            "limactl", "shell", _LIMA_INSTANCE, "--", "bash", "-c", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = proc

        # Read stdout line by line — setup.sh writes only @@SETUP: lines here
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            if text.startswith("@@SETUP:"):
                self._handle_setup_line(text)

        await proc.wait()
        if proc.returncode == 0:
            self._emit("done", {"message": "Provisioning complete"})
            self._status = "done"
        else:
            self._emit("error", {"message": f"Provisioning failed (exit {proc.returncode})"})
            self._status = "error"
            self._error = f"exit {proc.returncode}"

    def _handle_setup_line(self, line: str) -> None:
        """Parse @@SETUP:step_id:status:message and emit typed SSE events."""
        # Format: @@SETUP:<step_id>:<status>:<message>
        match = re.match(r"@@SETUP:([^:]+):([^:]+):(.*)", line)
        if not match:
            return
        step_id, status, message = match.group(1), match.group(2), match.group(3)

        if status == "start":
            self._emit("step_start", {"step": step_id, "message": message})
        elif status == "progress":
            self._emit("step_progress", {"step": step_id, "message": message})
        elif status == "done":
            self._emit("step_done", {"step": step_id, "message": message})
        elif status == "skip":
            self._emit("step_skip", {"step": step_id, "message": message})
        elif status == "error":
            self._emit("step_error", {"step": step_id, "message": message})
        elif status == "heartbeat":
            self._emit("heartbeat", {"step": step_id})

    async def check_markers(self) -> dict[str, object]:
        """Read VM-side marker files to determine provision state."""
        instance_status = await _lima_instance_status()
        if instance_status != "Running":
            return {"provisioned": False, "steps_done": [], "total_steps": len(_PROVISION_STEPS)}

        rc, stdout, _ = await _lima_shell(f"ls {_SETUP_MARKER_DIR}/*.done 2>/dev/null || true")
        if rc != 0 or not stdout.strip():
            return {"provisioned": False, "steps_done": [], "total_steps": len(_PROVISION_STEPS)}

        done_files = stdout.strip().splitlines()
        steps_done = sorted(
            os.path.basename(f).replace(".done", "")
            for f in done_files
        )
        all_ids = [s[0] for s in _PROVISION_STEPS]
        complete = all(sid in steps_done for sid in all_ids)
        return {
            "provisioned": complete,
            "steps_done": steps_done,
            "total_steps": len(_PROVISION_STEPS),
        }

    async def get_log(self) -> str:
        """Fetch the latest setup log from the VM."""
        rc, stdout, _ = await _lima_shell(
            f"ls -t {_SETUP_LOG_DIR}/setup-*.log 2>/dev/null | head -1 | xargs cat 2>/dev/null | tail -500",
            timeout=15,
        )
        return stdout if rc == 0 else ""


# ---------------------------------------------------------------------------
# Manager singletons (lazy, module-level)
# ---------------------------------------------------------------------------

_build_mgr: _BuildManager | None = None
_provision_mgr: _ProvisionManager | None = None


def _get_build_manager() -> _BuildManager:
    global _build_mgr  # noqa: PLW0603
    if _build_mgr is None:
        _build_mgr = _BuildManager()
    return _build_mgr


def _get_provision_manager() -> _ProvisionManager:
    global _provision_mgr  # noqa: PLW0603
    if _provision_mgr is None:
        _provision_mgr = _ProvisionManager()
    return _provision_mgr


# ---------------------------------------------------------------------------
# Build endpoints
# ---------------------------------------------------------------------------


@router.post("/vm/build")
async def build_vm() -> StreamingResponse:
    """Create or start the VM. Streams SSE progress events."""
    status = _vm_status()
    if not status.get("installed"):
        raise HTTPException(status_code=422, detail="VM backend (Lima) is not installed")

    mgr = _get_build_manager()
    if mgr._status != "running":
        await mgr.start()
    return StreamingResponse(mgr.stream(), media_type="text/event-stream")


@router.get("/vm/build/status")
async def get_build_status() -> dict[str, object]:
    """Check VM build / instance state."""
    mgr = _get_build_manager()
    result = dict(mgr.status_dict())
    if mgr._status in ("idle", "done", "error"):
        result["vm_state"] = await _lima_instance_status()
    return result


# ---------------------------------------------------------------------------
# Provision endpoints
# ---------------------------------------------------------------------------


@router.post("/vm/provision")
async def provision_vm(force: bool = False) -> StreamingResponse:
    """Run setup.sh inside the VM. Streams SSE progress events."""
    mgr = _get_provision_manager()
    if mgr._status != "running":
        await mgr.start(force=force)
    return StreamingResponse(mgr.stream(), media_type="text/event-stream")


@router.get("/vm/provision/status")
async def get_provision_status() -> dict[str, object]:
    """Check provisioning state (reads VM markers when idle)."""
    mgr = _get_provision_manager()
    result = dict(mgr.status_dict())
    if mgr._status in ("idle", "done", "error"):
        try:
            result["markers"] = await mgr.check_markers()
        except Exception:
            logger.debug("Could not read provision markers", exc_info=True)
            result["markers"] = None
    result["steps"] = [{"id": s[0], "label": s[1]} for s in _PROVISION_STEPS]
    return result


@router.post("/vm/provision/cancel")
async def cancel_provision() -> dict[str, object]:
    """Cancel an ongoing provisioning run."""
    mgr = _get_provision_manager()
    if mgr._status != "running":
        raise HTTPException(status_code=409, detail="No provisioning in progress")
    mgr.cancel()
    return {"cancelled": True}


@router.get("/vm/provision/log")
async def get_provision_log() -> Response:
    """Fetch the latest setup log from the VM."""
    mgr = _get_provision_manager()
    try:
        text = await mgr.get_log()
    except Exception:
        text = "(Could not read log — VM may not be running)"
    return Response(content=text, media_type="text/plain")
