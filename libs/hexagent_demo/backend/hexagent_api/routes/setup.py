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
import shlex
import shutil
import subprocess as _sp
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import AsyncIterator
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from hexagent_api.paths import data_dir, deps_dir, vm_lima_dir, vm_setup_dir, vm_setup_lite_dir

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
    """Return the *real* hardware architecture for Lima release asset names.

    ``platform.machine()`` lies when Python runs under Rosetta 2 on Apple
    Silicon — it returns ``x86_64`` instead of ``arm64``.  We detect this via
    ``sysctl.proc_translated`` (``1`` ⇒ Rosetta) and correct accordingly.

    Lima release naming differs by OS:
      - macOS (Darwin): ``arm64``, ``x86_64``
      - Linux:          ``aarch64``, ``x86_64``
    Since we only install Lima on macOS, we use macOS naming.
    """
    m = platform.machine().lower()

    # Detect Rosetta: Python reports x86_64 but real hardware is arm64
    if sys.platform == "darwin" and m == "x86_64":
        try:
            out = _sp.check_output(
                ["sysctl", "-n", "sysctl.proc_translated"],
                stderr=_sp.DEVNULL,
            )
            if out.decode().strip() == "1":
                return "arm64"
        except (OSError, _sp.CalledProcessError):
            pass

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


# ---------------------------------------------------------------------------
# WSL (Windows)
# ---------------------------------------------------------------------------

_WSL_INSTANCE = "hexagent"
_WSL_EXPORT_SOURCE = "Ubuntu"
_WSL_PREBUILT_CANDIDATES = (
    "hexagent-prebuilt.tar",
    "hexagent.tar",
    "ubuntu-base-24.04-amd64.tar.gz",
)


def _wsl_cmd() -> str | None:
    """Resolve path to ``wsl.exe``.

    Electron / minimal service environments sometimes omit ``System32`` from
    ``PATH``, which makes ``shutil.which`` fail even though WSL is installed.
    Fall back to the well-known location so ``/api/setup/vm`` reports
    ``installed: true`` and subprocess launches succeed.
    """
    w = shutil.which("wsl.exe") or shutil.which("wsl")
    if w:
        return w
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if not system_root:
        system_root = r"C:\Windows"
    candidate = Path(system_root) / "System32" / "wsl.exe"
    if candidate.is_file():
        return str(candidate)
    return None


def _decode_wsl_output(raw: bytes) -> str:
    if raw[:2] == b"\xff\xfe" or b"\x00" in raw:
        return raw.decode("utf-16-le", errors="replace").replace("\x00", "")
    return raw.decode("utf-8", errors="replace")


def _combine_wsl_output(stdout_b: bytes | None, stderr_b: bytes | None) -> str:
    """Decode and combine WSL stdout/stderr, preferring non-empty stderr first."""
    err = _decode_wsl_output(stderr_b or b"").strip()
    out = _decode_wsl_output(stdout_b or b"").strip()
    if err and out:
        return f"{err}\n{out}"
    return err or out


def _looks_like_wsl_usage(msg: str) -> bool:
    """Return True when output is the generic WSL usage/help banner."""
    text = msg.strip()
    low = text.lower()
    return (
        "usage: wsl" in low
        or "usage: wsl.exe" in low
        or "用法: wsl" in text
        or "用法: wsl.exe" in text
    )


def _looks_like_missing_wsl_disk(msg: str) -> bool:
    text = msg.lower()
    return (
        "error_path_not_found" in text
        or "mountdisk" in text
        or "ext4.vhdx" in text
    )


def _looks_like_wsl_localhost_proxy_warning(msg: str) -> bool:
    """Return True for known non-fatal WSL localhost-proxy warning text."""
    text = (msg or "").lower()
    return (
        ("localhost" in text and "proxy" in text and "wsl" in text and "nat" in text)
        or ("localhost 代理" in (msg or "") and "未镜像到 wsl" in (msg or ""))
    )


def _wsl2_blocker_reason(text: str) -> str | None:
    """Return a friendly reason when host cannot run WSL2."""
    t = (text or "").lower()
    blockers = (
        "does not support wsl2",
        "not support wsl2",
        "wsl2",
        "enablevirtualization",
        "virtual machine platform",
        "bios",
        "当前计算机配置不支持 wsl2",
        "虚拟机平台",
    )
    if any(k in t for k in blockers):
        return (
            "WSL2 is not available on this PC yet. Please enable "
            "'Virtual Machine Platform', ensure virtualization is enabled in BIOS, "
            "then reboot Windows and retry."
        )
    return None


def _probe_wsl2_readiness() -> tuple[bool, str | None]:
    """Check whether host is ready for WSL2-based distro import/start."""
    wsl = _wsl_cmd()
    if not wsl:
        return False, "wsl.exe not found"
    try:
        proc = _sp.run(
            [wsl, "--status"],
            stdout=_sp.PIPE,
            stderr=_sp.PIPE,
            timeout=8,
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("WSL readiness probe failed", exc_info=exc)
        return False, "Failed to probe WSL runtime"

    combined = _combine_wsl_output(proc.stdout, proc.stderr).strip()
    reason = _wsl2_blocker_reason(combined)
    if reason:
        return False, reason
    return True, None


def _parse_wsl_list(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if "NAME" in stripped.upper() and "STATE" in stripped.upper():
            continue
        if stripped.startswith("*"):
            stripped = stripped[1:].strip()
        parts = stripped.split()
        if len(parts) >= 3:
            entries.append({"name": parts[0], "state": parts[1], "version": parts[2]})
            continue
        # Older WSL builds may only return distro names with `wsl --list`.
        # Keep them with a synthetic state so downstream logic can still detect existence.
        if len(parts) == 1 and parts[0].lower() not in {"windows", "subsystem", "linux"}:
            entries.append({"name": parts[0], "state": "Unknown", "version": ""})
    return entries


async def _wsl_list() -> list[dict[str, str]]:
    wsl_exe = _wsl_cmd()
    if not wsl_exe:
        return []
    # Newer WSL supports `--list --verbose`, while older builds support `-l -v`
    # or only plain `--list`. Try all variants for best compatibility.
    variants = (
        ("--list", "--verbose"),
        ("-l", "-v"),
        ("--list",),
    )
    for args in variants:
        proc = await asyncio.create_subprocess_exec(
            wsl_exe,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out_b, _err_b = await proc.communicate()
        if proc.returncode != 0:
            continue
        parsed = _parse_wsl_list(_decode_wsl_output(out_b or b""))
        if parsed:
            return parsed
    return []


async def _wsl_instance_status() -> str | None:
    entries = await _wsl_list()
    for entry in entries:
        if entry["name"].lower() == _WSL_INSTANCE.lower():
            return entry["state"]
    return None


def _wsl_prebuilt_tar_path() -> Path | None:
    """Return an offline WSL rootfs archive if present.

    Search order:
    1. Backend-bundled VM assets (PyInstaller ``sandbox/vm/wsl/prebuilt``)
    2. Electron extraResources path from ``HEXAGENT_WSL_OFFLINE_DIR`` (if set)
    """
    candidate_dirs: list[Path] = [vm_setup_dir().parent / "wsl" / "prebuilt"]

    offline_dir = os.environ.get("HEXAGENT_WSL_OFFLINE_DIR", "").strip()
    if offline_dir:
        candidate_dirs.append(Path(offline_dir))

    for prebuilt_dir in candidate_dirs:
        for name in _WSL_PREBUILT_CANDIDATES:
            candidate = prebuilt_dir / name
            if candidate.is_file():
                return candidate
    return None


async def _wsl_probe_start() -> tuple[bool, str]:
    """Best-effort probe that distro can actually start.

    This catches cases where `wsl -l -v` still lists the distro (Stopped),
    but its backing VHDX path is missing/corrupted.
    """
    wsl_exe = _wsl_cmd()
    if not wsl_exe:
        return False, "wsl.exe not found"
    proc = await asyncio.create_subprocess_exec(
        wsl_exe,
        "-d",
        _WSL_INSTANCE,
        "--",
        "echo",
        "ok",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=20)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return False, "WSL start probe timed out"
    if (proc.returncode or 0) == 0:
        return True, ""
    return False, _combine_wsl_output(stdout_b, stderr_b)


async def _wait_for_wsl_vhdx(import_dir: Path, timeout_s: float = 45.0) -> Path | None:
    """Wait until WSL import materializes ``ext4.vhdx`` under ``import_dir``.

    On some Windows hosts `wsl --import` returns before the VHDX file is fully
    visible to subsequent `wsl -d` start attempts, which can cause transient
    `MountDisk ... ERROR_PATH_NOT_FOUND`.
    """
    target = import_dir / "ext4.vhdx"
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if target.is_file():
            return target
        await asyncio.sleep(0.5)
    return None


# ``wsl -l -v`` uses the Windows display language for the STATE column.
# Cowork only needs the ``hexagent`` distro to exist; WSL starts it on demand.
_WSL_COWORK_READY_STATES = frozenset(
    {
        "Running",
        "Stopped",
        "正在运行",
        "已停止",
    }
)

_WSL_RUNNING_STATES = frozenset(
    {
        "Running",
        "姝ｅ湪杩愯",
    }
)

_WSL_STOPPED_STATES = frozenset(
    {
        "Stopped",
        "宸插仠姝?",
    }
)


def _wsl_distro_ready_for_cowork(state: str | None) -> bool:
    """Return True if the cowork distro exists and has a non-empty state.

    ``wsl -l -v`` localizes the STATE column by OS language, so exact
    string matching is fragile. For cowork we only need the distro to
    exist; WSL can start it on-demand when it's stopped.
    """
    return bool(state and state.strip())


def _wsl_state_equals(state: str | None, accepted: frozenset[str]) -> bool:
    """Locale-tolerant WSL state check."""
    return bool(state and state.strip() in accepted)


def _pick_wsl_source_distro(entries: list[dict[str, str]]) -> str | None:
    """Pick an Ubuntu source distro name from installed WSL distributions.

    Prefers an exact ``Ubuntu`` match, then falls back to common
    versioned names such as ``Ubuntu-22.04`` / ``Ubuntu-24.04``.
    """
    exact = next((e["name"] for e in entries if e["name"].lower() == _WSL_EXPORT_SOURCE.lower()), None)
    if exact:
        return exact
    return next((e["name"] for e in entries if e["name"].lower().startswith("ubuntu")), None)


def _wsl_status() -> dict[str, object]:
    wsl = _wsl_cmd()
    if not wsl:
        return {"installed": False, "path": None, "managed": False}

    ready, reason = _probe_wsl2_readiness()
    if not ready:
        return {
            "installed": False,
            "path": wsl,
            "managed": False,
            "reason": reason or "WSL runtime is not available",
        }

    # `wsl.exe` may exist even when WSL optional components are not enabled.
    # Probe command success instead of relying on binary presence.
    probe_variants = (
        ("--status",),
        ("--list", "--verbose"),
        ("-l", "-v"),
        ("--list",),
    )
    last_err = ""
    for args in probe_variants:
        try:
            proc = _sp.run(
                [wsl, *args],
                stdout=_sp.PIPE,
                stderr=_sp.PIPE,
                timeout=8,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("WSL status probe failed for args=%s", args, exc_info=exc)
            last_err = "Failed to probe WSL runtime"
            continue

        if proc.returncode == 0:
            return {"installed": True, "path": wsl, "managed": False}
        last_err = _combine_wsl_output(proc.stdout, proc.stderr).strip() or last_err

    return {
        "installed": False,
        "path": wsl,
        "managed": False,
        # Some Windows builds print only usage text for unsupported probes.
        # Treat that as "not installed yet" (pending) instead of hard error.
        **({} if _looks_like_wsl_usage(last_err) else {"reason": last_err or "WSL runtime is not available"}),
    }


def _win_path_to_wsl(path: Path | str) -> str:
    s = str(path).replace("\\", "/")
    m = re.match(r"^([A-Za-z]):(.*)$", s)
    if not m:
        raise ValueError(f"Unsupported Windows path for WSL conversion: {s}")
    drive = m.group(1).lower()
    rest = m.group(2)
    if not rest.startswith("/"):
        rest = "/" + rest
    return f"/mnt/{drive}{rest}"


async def _wsl_shell(
    cmd: str,
    *,
    timeout: float = 60,
    user: str | None = None,
) -> tuple[int, str, str]:
    wsl_exe = _wsl_cmd()
    if not wsl_exe:
        return 1, "", "wsl.exe not found"
    exec_args: list[str] = [wsl_exe, "-d", _WSL_INSTANCE]
    if user:
        exec_args.extend(["-u", user])
    exec_args.extend(["--", "bash", "-lc", cmd])
    proc = await asyncio.create_subprocess_exec(
        *exec_args,
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
        _decode_wsl_output(stdout_b or b""),
        _decode_wsl_output(stderr_b or b""),
    )


async def _install_lima_stream():
    """SSE generator that downloads and installs Lima."""
    def sse(event: str, data: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    yield sse("progress", {"step": "resolving", "message": "Resolving latest Lima version..."})

    version = await _resolve_lima_version()
    yield sse("progress", {"step": "downloading", "message": f"Downloading Lima v{version}..."})

    tmp_dir = tempfile.mkdtemp(prefix="hexagent_lima_")
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

        # Strip macOS quarantine flag so Gatekeeper doesn't block the binary
        proc = await asyncio.create_subprocess_exec(
            "xattr", "-dr", "com.apple.quarantine", str(_lima_dir()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()  # best-effort, ignore errors

        # Ad-hoc codesign limactl with virtualization entitlement (required for VZ on macOS)
        entitlements = vm_lima_dir() / "entitlements.plist"
        if entitlements.is_file():
            proc = await asyncio.create_subprocess_exec(
                "codesign", "--force", "--sign", "-",
                "--entitlements", str(entitlements),
                str(_lima_bin()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning("codesign limactl failed: %s", (stderr or b"").decode(errors="replace"))

        _ensure_managed_lima_on_path()
        yield sse("done", {"message": f"Lima v{version} installed successfully", "path": str(_lima_bin())})

    except Exception:
        logger.exception("Lima installation failed")
        yield sse("error", {"message": "Lima installation failed. Check server logs for details."})
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _install_wsl_stream():
    """SSE generator that enables WSL on Windows."""
    def sse(event: str, data: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    wsl = _wsl_cmd()
    if wsl:
        yield sse("done", {"message": f"WSL already installed ({wsl})"})
        return

    yield sse("progress", {"step": "installing", "message": "Installing WSL components..."})
    # ``wsl.exe`` may exist in System32 even when not on PATH
    wsl_for_install = _wsl_cmd() or str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "wsl.exe")
    proc = await asyncio.create_subprocess_exec(
        wsl_for_install,
        "--install",
        "--no-distribution",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out_b, err_b = await proc.communicate()
    out = _decode_wsl_output(out_b or b"").strip()
    err = _decode_wsl_output(err_b or b"").strip()
    if proc.returncode != 0:
        msg = err or out or "Failed to install WSL. Please run 'wsl --install' as Administrator."
        yield sse("error", {"message": msg})
        return

    yield sse("done", {"message": "WSL installed. A reboot may be required before continuing."})


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
        return {"supported": True, "backend": "wsl", **_wsl_status()}
    return {"supported": False, "backend": None, "installed": False, "reason": f"No VM backend for {sys.platform}"}


def _runtime_vm_backend() -> str:
    """Resolve the active VM backend for branch dispatch.

    Prefer the backend reported by ``_vm_status()`` so behavior stays aligned
    with the setup API surface. Fall back to platform defaults defensively.
    """
    backend = str(_vm_status().get("backend") or "")
    if backend in {"wsl", "lima"}:
        return backend
    if sys.platform == "win32":
        return "wsl"
    if sys.platform == "darwin":
        return "lima"
    return ""


# ---------------------------------------------------------------------------
# Endpoints — generic /vm, frontend doesn't need to know Lima vs WSL
# ---------------------------------------------------------------------------


@router.get("/vm")
async def get_vm_status() -> dict[str, object]:
    """Check whether the VM backend is available.

    Returns ``vm_ready: true`` when cowork can start: Lima needs the instance
    **Running**; WSL accepts **Running** or **Stopped** (distro exists — WSL
    starts it on first ``wsl -d``). Localized ``wsl -l -v`` state strings are
    recognized where known.
    """
    result = _vm_status()

    vm_ready = False
    instance_status: str | None = None
    instance_error: str | None = None
    if result.get("installed"):
        try:
            if result.get("backend") == "lima":
                instance_status = await _lima_instance_status()
                vm_ready = instance_status == "Running"
            elif result.get("backend") == "wsl":
                instance_status = await _wsl_instance_status()
                vm_ready = _wsl_distro_ready_for_cowork(instance_status)
                if vm_ready:
                    ok, err = await _wsl_probe_start()
                    if not ok:
                        vm_ready = False
                        instance_error = err or "WSL distro exists but failed to start"
        except Exception:
            pass

    result["instance_status"] = instance_status
    if instance_error:
        result["instance_error"] = instance_error
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
    if backend == "wsl":
        return StreamingResponse(_install_wsl_stream(), media_type="text/event-stream")

    raise HTTPException(status_code=501, detail=f"Auto-install not yet supported for {backend}")


# ---------------------------------------------------------------------------
# Process Manager — base class for long-running subprocess operations
# ---------------------------------------------------------------------------
# Decouples subprocess lifecycle from HTTP request lifecycle so that:
#   - Provisioning continues if the SSE connection drops (tab close)
#   - Reconnecting clients replay buffered events + tail new ones
#   - Multiple concurrent viewers are supported
# ---------------------------------------------------------------------------

_LIMA_INSTANCE = "hexagent"


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
        except Exception:
            logger.exception("%s failed", self.__class__.__name__)
            self._status = "error"
            self._error = "Internal error"
            self._emit("error", {"message": "An internal error occurred — check server logs for details."})
        finally:
            self._new_event.set()


# ---------------------------------------------------------------------------
# Build Manager — creates / starts the Lima VM
# ---------------------------------------------------------------------------


async def _ensure_limactl_entitlement() -> None:
    """Verify limactl has the virtualization entitlement; re-sign if missing.

    Without ``com.apple.security.virtualization``, the VZ backend will refuse
    to start with ``VZErrorDomain Code=2``.  This can happen when the binary
    was installed from a GitHub tarball, built from source, or had its
    signature stripped by another tool.
    """
    limactl = shutil.which("limactl")
    if not limactl:
        return

    # Check current entitlements
    proc = await asyncio.create_subprocess_exec(
        "codesign", "-d", "--entitlements", "-", "--xml", limactl,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if b"com.apple.security.virtualization" in stdout:
        return  # already has the entitlement

    logger.info("limactl at %s is missing virtualization entitlement, attempting to re-sign", limactl)

    entitlements = vm_lima_dir() / "entitlements.plist"
    if not entitlements.is_file():
        logger.warning("Cannot re-sign limactl: entitlements.plist not found at %s", entitlements)
        return

    proc = await asyncio.create_subprocess_exec(
        "codesign", "--force", "--sign", "-",
        "--entitlements", str(entitlements),
        limactl,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning(
            "Failed to re-sign limactl with virtualization entitlement: %s",
            (stderr or b"").decode(errors="replace"),
        )


class _BuildManager(_ProcessManager):
    """Manages ``limactl start`` to create or boot the VM."""

    async def _communicate_with_heartbeat(
        self,
        proc: asyncio.subprocess.Process,
        *,
        step: str,
        message: str,
        heartbeat_seconds: float = 5.0,
        progress_info: Callable[[], str] | None = None,
    ) -> tuple[bytes, bytes]:
        """Wait for process completion while emitting periodic progress heartbeats."""
        started = asyncio.get_running_loop().time()
        comm_task = asyncio.create_task(proc.communicate())
        while True:
            done, _ = await asyncio.wait({comm_task}, timeout=heartbeat_seconds)
            if done:
                stdout_b, stderr_b = comm_task.result()
                return stdout_b, stderr_b
            elapsed = int(asyncio.get_running_loop().time() - started)
            extra = ""
            if progress_info is not None:
                try:
                    detail = progress_info().strip()
                    if detail:
                        extra = f" {detail}"
                except Exception:
                    extra = ""
            self._emit("progress", {"step": step, "message": f"{message} (elapsed {elapsed}s){extra}"})

    async def _run(self, **kwargs: object) -> None:
        backend = _runtime_vm_backend()
        if backend == "wsl":
            await self._run_wsl()
            return
        if backend == "lima":
            await self._run_lima()
            return
        self._emit("error", {"message": f"VM build is not supported on backend: {backend or sys.platform}"})
        self._status = "error"
        self._error = "Unsupported backend"

    async def _start_wsl_instance(
        self,
        wsl_exe: str,
        *,
        step: str,
        message: str,
        retries_on_missing_disk: int = 0,
    ) -> tuple[bool, str]:
        """Start hexagent distro and optionally retry transient missing-disk errors."""
        attempts = max(1, retries_on_missing_disk + 1)
        for attempt in range(1, attempts + 1):
            proc = await asyncio.create_subprocess_exec(
                wsl_exe, "-d", _WSL_INSTANCE, "--", "echo", "ok",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._process = proc
            out_b, err_b = await self._communicate_with_heartbeat(
                proc,
                step=step,
                message=message,
            )
            if proc.returncode == 0:
                return True, ""

            err = _combine_wsl_output(out_b, err_b)
            is_missing_disk = _looks_like_missing_wsl_disk(err)
            if is_missing_disk and attempt < attempts:
                wait_s = min(2 * attempt, 5)
                self._emit(
                    "progress",
                    {
                        "step": step,
                        "message": f"WSL disk not ready yet, retrying start in {wait_s}s "
                        f"({attempt}/{attempts - 1})...",
                    },
                )
                await asyncio.sleep(wait_s)
                continue

            return False, err or f"WSL start failed (exit {proc.returncode})"
        return False, "WSL start failed"

    async def _run_lima(self) -> None:
        # Ensure limactl has the virtualization entitlement before any VM
        # operation — otherwise VZ will fail with a cryptic entitlement error.
        await _ensure_limactl_entitlement()

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
            last_line = await self._stream_stderr(proc)
            await proc.wait()
            if proc.returncode == 0:
                self._emit("done", {"message": "VM started successfully"})
                self._status = "done"
            else:
                detail = f" — {last_line}" if last_line else ""
                self._emit("error", {"message": f"VM start failed (exit {proc.returncode}){detail}"})
                self._status = "error"
                self._error = f"exit {proc.returncode}"
            return

        # Instance doesn't exist — full build
        yaml_path = vm_lima_dir() / "hexagent.yaml"
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
        last_line = await self._stream_stderr(proc)
        await proc.wait()
        if proc.returncode == 0:
            self._emit("done", {"message": "VM created successfully"})
            self._status = "done"
        else:
            detail = f" — {last_line}" if last_line else ""
            self._emit("error", {"message": f"VM creation failed (exit {proc.returncode}){detail}"})
            self._status = "error"
            self._error = f"exit {proc.returncode}"

    async def _run_wsl(self) -> None:
        wsl_exe = _wsl_cmd()
        if not wsl_exe:
            self._emit("error", {"message": "WSL is not installed. Install it first in Phase 1."})
            self._status = "error"
            self._error = "WSL missing"
            return

        ready, reason = _probe_wsl2_readiness()
        if not ready:
            self._emit("error", {"message": reason or "WSL2 runtime is not ready"})
            self._status = "error"
            self._error = "WSL2 not ready"
            return

        status = await _wsl_instance_status()
        if _wsl_state_equals(status, _WSL_RUNNING_STATES):
            self._emit("done", {"message": "WSL distro is already running"})
            self._status = "done"
            return

        if _wsl_state_equals(status, _WSL_STOPPED_STATES):
            self._emit("progress", {"step": "starting", "message": "Starting existing WSL distro..."})
            ok, err = await self._start_wsl_instance(
                wsl_exe,
                step="starting",
                message="Starting existing WSL distro...",
                retries_on_missing_disk=1,
            )
            if ok:
                self._emit("done", {"message": "WSL distro started successfully"})
                self._status = "done"
                return
            else:
                if _looks_like_missing_wsl_disk(err):
                    self._emit("progress", {"step": "creating", "message": "Detected broken WSL distro disk. Recreating HexAgent distro..."})
                    proc_unreg = await asyncio.create_subprocess_exec(
                        wsl_exe, "--unregister", _WSL_INSTANCE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    self._process = proc_unreg
                    u_out_b, u_err_b = await self._communicate_with_heartbeat(
                        proc_unreg,
                        step="creating",
                        message="Removing broken HexAgent WSL distro...",
                    )
                    if proc_unreg.returncode != 0:
                        u_err = _combine_wsl_output(u_out_b, u_err_b)
                        self._emit("error", {"message": u_err or f"WSL unregister failed (exit {proc_unreg.returncode})"})
                        self._status = "error"
                        self._error = f"exit {proc_unreg.returncode}"
                        return
                    # Continue with fresh-create flow below.
                else:
                    self._emit("error", {"message": err or f"WSL start failed (exit {proc.returncode})"})
                    self._status = "error"
                    self._error = f"exit {proc.returncode}"
                    return

        prebuilt_tar = _wsl_prebuilt_tar_path()
        import_dir = data_dir() / "wsl" / _WSL_INSTANCE / "disk"

        # Distro does not exist: prefer bundled prebuilt HexAgent rootfs.
        if prebuilt_tar is not None:
            self._emit("progress", {"step": "creating", "message": "Importing bundled HexAgent VM image..."})
            if import_dir.exists():
                shutil.rmtree(import_dir, ignore_errors=True)
            import_dir.mkdir(parents=True, exist_ok=True)

            proc_import = await asyncio.create_subprocess_exec(
                wsl_exe, "--import", _WSL_INSTANCE, str(import_dir), str(prebuilt_tar), "--version", "2",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._process = proc_import
            _, err_b = await self._communicate_with_heartbeat(
                proc_import,
                step="creating",
                message="Importing bundled HexAgent VM image...",
                progress_info=lambda: f"(image ~{(prebuilt_tar.stat().st_size / (1024 * 1024)):.1f} MB)",
            )
            if proc_import.returncode != 0:
                err = _decode_wsl_output(err_b or b"").strip()
                self._emit("error", {"message": err or f"Bundled image import failed (exit {proc_import.returncode})"})
                self._status = "error"
                self._error = f"exit {proc_import.returncode}"
                return

            self._emit("progress", {"step": "starting", "message": "Finalizing imported WSL disk..."})
            await _wait_for_wsl_vhdx(import_dir)
            self._emit("progress", {"step": "starting", "message": "Starting imported HexAgent WSL distro..."})
            ok, err = await self._start_wsl_instance(
                wsl_exe,
                step="starting",
                message="Starting imported HexAgent WSL distro...",
                retries_on_missing_disk=6,
            )
            if ok:
                self._emit("done", {"message": "WSL distro imported from bundled image and started successfully"})
                self._status = "done"
            else:
                self._emit("error", {"message": err})
                self._status = "error"
                self._error = err
            return

        # Fallback: bootstrap from Ubuntu export.
        self._emit("progress", {"step": "creating", "message": "Preparing source distro (Ubuntu)..."})
        entries = await _wsl_list()
        source_distro = _pick_wsl_source_distro(entries)
        if source_distro is None:
            proc = await asyncio.create_subprocess_exec(
                wsl_exe, "--install", "-d", _WSL_EXPORT_SOURCE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._process = proc
            out_b, err_b = await self._communicate_with_heartbeat(
                proc,
                step="creating",
                message="Preparing source distro (Ubuntu)...",
            )
            if proc.returncode != 0:
                err = (_decode_wsl_output(err_b or b"") or _decode_wsl_output(out_b or b"")).strip()
                self._emit(
                    "error",
                    {"message": err or "Failed to install Ubuntu distro. Try running `wsl --install -d Ubuntu` manually once."},
                )
                self._status = "error"
                self._error = f"exit {proc.returncode}"
                return
            self._emit("progress", {"step": "creating", "message": "Ubuntu installed. Continuing..."})
            entries = await _wsl_list()
            source_distro = _pick_wsl_source_distro(entries)
            if source_distro is None:
                self._emit(
                    "error",
                    {"message": "Ubuntu distro was installed but could not be found in `wsl --list --verbose`."},
                )
                self._status = "error"
                self._error = "Ubuntu source distro not found after install"
                return

        export_root = deps_dir() / "wsl"
        export_root.mkdir(parents=True, exist_ok=True)
        export_tar = export_root / f"{source_distro.lower()}-seed.tar"
        import_dir.mkdir(parents=True, exist_ok=True)

        self._emit("progress", {"step": "creating", "message": "Exporting Ubuntu rootfs..."})
        proc_export = await asyncio.create_subprocess_exec(
            wsl_exe, "--export", source_distro, str(export_tar),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = proc_export
        _, err_b = await self._communicate_with_heartbeat(
            proc_export,
            step="creating",
            message="Exporting Ubuntu rootfs...",
            progress_info=lambda: f"(exported ~{(export_tar.stat().st_size / (1024 * 1024)):.1f} MB)" if export_tar.exists() else "",
        )
        if proc_export.returncode != 0:
            err = _decode_wsl_output(err_b or b"").strip()
            self._emit("error", {"message": err or f"WSL export failed (exit {proc_export.returncode})"})
            self._status = "error"
            self._error = f"exit {proc_export.returncode}"
            return

        self._emit("progress", {"step": "creating", "message": "Importing HexAgent WSL distro..."})
        proc_import = await asyncio.create_subprocess_exec(
            wsl_exe, "--import", _WSL_INSTANCE, str(import_dir), str(export_tar), "--version", "2",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = proc_import
        _, err_b = await self._communicate_with_heartbeat(
            proc_import,
            step="creating",
            message="Importing HexAgent WSL distro...",
        )
        if proc_import.returncode != 0:
            err = _decode_wsl_output(err_b or b"").strip()
            self._emit("error", {"message": err or f"WSL import failed (exit {proc_import.returncode})"})
            self._status = "error"
            self._error = f"exit {proc_import.returncode}"
            return

        self._emit("progress", {"step": "starting", "message": "Finalizing imported WSL disk..."})
        await _wait_for_wsl_vhdx(import_dir)
        self._emit("progress", {"step": "starting", "message": "Starting HexAgent WSL distro..."})
        ok, err = await self._start_wsl_instance(
            wsl_exe,
            step="starting",
            message="Starting HexAgent WSL distro...",
            retries_on_missing_disk=6,
        )
        if ok:
            self._emit("done", {"message": "WSL distro created and started successfully"})
            self._status = "done"
        else:
            self._emit("error", {"message": err})
            self._status = "error"
            self._error = err

    async def _stream_stderr(self, proc: asyncio.subprocess.Process) -> str:
        """Read limactl stderr line-by-line and emit progress events.

        Returns the last non-empty stderr line (useful for error context).
        """
        assert proc.stderr is not None
        last_line = ""
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            last_line = text
            # Heuristic progress from limactl output
            if "Downloading" in text or "downloading" in text:
                self._emit("progress", {"step": "downloading", "message": text})
            elif "Waiting" in text or "Booting" in text:
                self._emit("progress", {"step": "booting", "message": text})
            elif "READY" in text or "ready" in text:
                self._emit("progress", {"step": "ready", "message": text})
            else:
                self._emit("progress", {"step": "output", "message": text})
        return last_line


# ---------------------------------------------------------------------------
# Provision Manager — runs setup.sh inside the VM
# ---------------------------------------------------------------------------

_SETUP_MARKER_DIRS = ("/var/lib/hexagent/setup", "/var/lib/openagent/setup")
_SETUP_LOG_DIRS = ("/var/log/hexagent/setup", "/var/log/openagent/setup")
_SETUP_VM_DIR = "/tmp/hexagent-setup"

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
        backend = _runtime_vm_backend()
        if backend == "wsl":
            await self._run_wsl(**kwargs)
            return
        if backend == "lima":
            await self._run_lima(**kwargs)
            return
        self._emit("error", {"message": f"VM provisioning is not supported on backend: {backend or sys.platform}"})
        self._status = "error"
        self._error = "Unsupported backend"

    async def _run_lima(self, **kwargs: object) -> None:
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
        setup_dir = vm_setup_lite_dir()
        if not setup_dir.is_dir():
            self._emit("error", {"message": f"Setup directory not found: {setup_dir}"})
            self._status = "error"
            self._error = "Setup dir not found"
            return

        # Tar locally, copy tarball, extract in VM
        with tempfile.TemporaryDirectory(prefix="hexagent_setup_") as tmp:
            tar_path = os.path.join(tmp, "setup.tar.gz")
            _sp.run(
                ["tar", "-czf", tar_path, "-C", str(setup_dir.parent), setup_dir.name],
                check=True,
            )
            copy_proc = await asyncio.create_subprocess_exec(
                "limactl", "copy", tar_path, f"{_LIMA_INSTANCE}:/tmp/hexagent-setup.tar.gz",
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
            f"sudo tar -xzf /tmp/hexagent-setup.tar.gz -C {_SETUP_VM_DIR} --strip-components=1 && "
            f"rm -f /tmp/hexagent-setup.tar.gz",
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

    async def _run_wsl(self, **kwargs: object) -> None:
        force = bool(kwargs.get("force", False))
        instance_status = await _wsl_instance_status()
        # Keep cowork behavior consistent with /api/setup/vm:
        # distro may be Stopped but still ready; start it on-demand.
        if not _wsl_distro_ready_for_cowork(instance_status):
            self._emit("error", {"message": f"WSL distro is not available (status: {instance_status})"})
            self._status = "error"
            self._error = "WSL distro unavailable"
            return
        if not _wsl_state_equals(instance_status, _WSL_RUNNING_STATES):
            self._emit("progress", {"step": "starting", "message": "Starting WSL distro for provisioning..."})
            wsl_exe = _wsl_cmd()
            if not wsl_exe:
                self._emit("error", {"message": "wsl.exe not found - cannot provision"})
                self._status = "error"
                self._error = "WSL missing"
                return
            proc_start = await asyncio.create_subprocess_exec(
                wsl_exe, "-d", _WSL_INSTANCE, "--", "echo", "ok",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._process = proc_start
            stdout_b, stderr_b = await proc_start.communicate()
            if proc_start.returncode != 0:
                err = _combine_wsl_output(stdout_b, stderr_b)
                self._emit("error", {"message": err or f"WSL start failed (exit {proc_start.returncode})"})
                self._status = "error"
                self._error = f"exit {proc_start.returncode}"
                return

        self._emit("progress", {"step": "copying", "message": "Preparing setup files in WSL..."})
        setup_dir = vm_setup_lite_dir()
        if not setup_dir.is_dir():
            self._emit("error", {"message": f"Setup directory not found: {setup_dir}"})
            self._status = "error"
            self._error = "Setup dir not found"
            return

        setup_wsl = _win_path_to_wsl(setup_dir)
        setup_wsl_quoted = shlex.quote(setup_wsl)
        setup_vm_dir_quoted = shlex.quote(_SETUP_VM_DIR)
        rc, _, err = await _wsl_shell(
            f"rm -rf {setup_vm_dir_quoted} && mkdir -p {setup_vm_dir_quoted} && "
            f"cp -r {setup_wsl_quoted}/. {setup_vm_dir_quoted}/ && "
            f"find {setup_vm_dir_quoted} -type f -name '*.sh' -exec sed -i 's/\\r$//' {{}} + && "
            f"find {setup_vm_dir_quoted} -type f -name '*.sh' -exec chmod +x {{}} +",
            timeout=60,
            user="root",
        )
        if rc != 0:
            # Some WSL builds emit a localhost-proxy warning under NAT mode,
            # and may still finish staging. Verify before failing hard.
            if _looks_like_wsl_localhost_proxy_warning(err):
                verify_rc, _, verify_err = await _wsl_shell(
                    f"test -f {setup_vm_dir_quoted}/setup.sh && test -d {setup_vm_dir_quoted}/steps",
                    timeout=15,
                    user="root",
                )
                if verify_rc == 0:
                    self._emit(
                        "progress",
                        {
                            "step": "copying",
                            "message": "WSL reported localhost proxy warning, but setup files were staged successfully. Continuing...",
                        },
                    )
                else:
                    self._emit(
                        "error",
                        {
                            "message": (
                                f"Failed to stage setup files in WSL: {err}"
                                + (f"\nVerification error: {verify_err}" if verify_err else "")
                            )
                        },
                    )
                    self._status = "error"
                    self._error = "Stage failed"
                    return
            else:
                self._emit("error", {"message": f"Failed to stage setup files in WSL: {err}"})
                self._status = "error"
                self._error = "Stage failed"
                return

        self._emit("progress", {"step": "starting", "message": "Starting provisioning..."})
        cmd = f"bash {_SETUP_VM_DIR}/setup.sh"
        if force:
            cmd += " --force"

        wsl_exe = _wsl_cmd()
        if not wsl_exe:
            self._emit("error", {"message": "wsl.exe not found — cannot provision"})
            self._status = "error"
            self._error = "WSL missing"
            return

        proc = await asyncio.create_subprocess_exec(
            wsl_exe, "-d", _WSL_INSTANCE, "-u", "root", "--", "bash", "-lc", cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._process = proc

        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
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
        backend = _runtime_vm_backend()
        if backend == "wsl":
            instance_status = await _wsl_instance_status()
            shell = lambda cmd: _wsl_shell(cmd, user="root")
            if not _wsl_distro_ready_for_cowork(instance_status):
                return {"provisioned": False, "steps_done": [], "total_steps": len(_PROVISION_STEPS)}
        elif backend == "lima":
            instance_status = await _lima_instance_status()
            shell = _lima_shell
            if instance_status != "Running":
                return {"provisioned": False, "steps_done": [], "total_steps": len(_PROVISION_STEPS)}
        else:
            return {"provisioned": False, "steps_done": [], "total_steps": len(_PROVISION_STEPS)}

        stdout = ""
        for marker_dir in _SETUP_MARKER_DIRS:
            rc, out, _ = await shell(f"ls {marker_dir}/*.done 2>/dev/null || true")
            if rc == 0 and out.strip():
                stdout = out
                break
        if not stdout.strip():
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
        backend = _runtime_vm_backend()
        if backend == "wsl":
            shell = lambda cmd, timeout=15: _wsl_shell(cmd, timeout=timeout, user="root")
        elif backend == "lima":
            shell = _lima_shell
        else:
            return ""
        for log_dir in _SETUP_LOG_DIRS:
            rc, stdout, _ = await shell(
                f"ls -t {log_dir}/setup-*.log 2>/dev/null | head -1 | xargs cat 2>/dev/null | tail -500",
                timeout=15,
            )
            if rc == 0 and stdout.strip():
                return stdout
        return ""


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
        backend = status.get("backend") or "vm backend"
        raise HTTPException(status_code=422, detail=f"VM backend ({backend}) is not installed")

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
        backend = _runtime_vm_backend()
        if backend == "wsl":
            result["vm_state"] = await _wsl_instance_status()
        elif backend == "lima":
            result["vm_state"] = await _lima_instance_status()
        else:
            result["vm_state"] = None
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
