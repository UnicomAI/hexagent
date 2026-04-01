"""macOS / Lima VM backend — installation, build, and provisioning.

This module is only loaded on macOS (darwin).  All Lima-specific logic lives
here so that the Windows-side setup.py stays free of macOS dependencies.

Public API consumed by setup.py:
    lima_status()                  — installation check
    ensure_managed_lima_on_path()  — prepend managed Lima bin to PATH
    install_lima_stream()          — SSE generator for Lima install
    lima_shell()                   — run a command inside the Lima VM
    lima_instance_status()         — get Lima instance status string
    build_run_lima(mgr)            — drive _BuildManager for Lima
    provision_run_lima(mgr, **kw)  — drive _ProvisionManager for Lima
"""
from __future__ import annotations

import asyncio
import contextlib
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

from hexagent_api.paths import deps_dir, vm_lima_dir, vm_setup_lite_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LIMA_INSTANCE = "hexagent"

_LIMA_FALLBACK_VERSION = "2.1.0"
_LIMA_MAJOR = 2  # Accept v2.x.x releases only

_LIMA_PREBUILT_CANDIDATES = (
    "hexagent-prebuilt.tar.gz",
    "hexagent-prebuilt.tar",
)

_LIMA_RELEASES_API = "https://api.github.com/repos/lima-vm/lima/releases"
_LIMA_RELEASE_URL = (
    "https://github.com/lima-vm/lima/releases/download"
    "/v{version}/lima-{version}-{os}-{arch}.tar.gz"
)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# Set to True when the VM was restored from a prebuilt archive that already
# has all provisioning steps baked in — provisioning can be skipped entirely.
_vm_restored_from_prebuilt: bool = False

# ---------------------------------------------------------------------------
# Architecture / path helpers
# ---------------------------------------------------------------------------


def _lima_dir() -> Path:
    return deps_dir() / "lima"


def _lima_bin() -> Path:
    return _lima_dir() / "bin" / "limactl"


def _resolve_arch() -> str:
    """Return the *real* hardware architecture for Lima release asset names.

    ``platform.machine()`` lies when Python runs under Rosetta 2 on Apple
    Silicon — it returns ``x86_64`` instead of ``arm64``.  We detect this via
    ``sysctl.proc_translated`` (``1`` ⇒ Rosetta) and correct accordingly.
    """
    m = platform.machine().lower()

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
    """Fetch the latest *downloadable* stable Lima v{_LIMA_MAJOR}.x version."""
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

    if _LIMA_FALLBACK_VERSION not in candidates:
        candidates.append(_LIMA_FALLBACK_VERSION)

    for version in candidates:
        url = _lima_tarball_url(version)
        if await _check_url_exists(url):
            return version

    return candidates[0]


def _lima_tarball_url(version: str) -> str:
    return _LIMA_RELEASE_URL.format(
        version=version,
        os="Darwin",
        arch=_resolve_arch(),
    )


def _lima_prebuilt_tar_path() -> Path | None:
    """Return a prebuilt Lima instance archive if present."""
    candidate_dirs: list[Path] = [vm_lima_dir() / "prebuilt"]

    offline_dir = os.environ.get("HEXAGENT_LIMA_OFFLINE_DIR", "").strip()
    if offline_dir:
        candidate_dirs.append(Path(offline_dir))

    for prebuilt_dir in candidate_dirs:
        for name in _LIMA_PREBUILT_CANDIDATES:
            candidate = prebuilt_dir / name
            if candidate.is_file():
                return candidate
    return None


def _lima_offline_tarball_path() -> Path | None:
    """Return a bundled Lima release tarball if present in HEXAGENT_LIMA_OFFLINE_DIR."""
    offline_dir = os.environ.get("HEXAGENT_LIMA_OFFLINE_DIR", "").strip()
    if not offline_dir:
        return None

    arch = _resolve_arch()
    offline_path = Path(offline_dir)
    try:
        for entry in offline_path.iterdir():
            if entry.is_file() and entry.name.startswith("lima-") and entry.name.endswith(f"-Darwin-{arch}.tar.gz"):
                return entry
    except OSError:
        pass
    return None


def _lima_offline_image_path() -> Path | None:
    """Return a local Ubuntu cloud image for offline Lima VM creation, if present."""
    arch = _resolve_arch()
    ubuntu_arch = "arm64" if arch == "arm64" else "amd64"
    candidate_names = (f"ubuntu-24.04-minimal-cloudimg-{ubuntu_arch}.img",)

    offline_dir = os.environ.get("HEXAGENT_LIMA_OFFLINE_DIR", "").strip()
    if not offline_dir:
        return None

    offline_path = Path(offline_dir)
    for name in candidate_names:
        candidate = offline_path / name
        try:
            if candidate.is_file() and candidate.stat().st_size > 50 * 1024 * 1024:
                return candidate
        except OSError:
            continue
    return None


def ensure_managed_lima_on_path() -> None:
    """Prepend the managed Lima bin dir to PATH if it exists."""
    if _lima_bin().is_file():
        bin_dir = str(_lima_bin().parent)
        path = os.environ.get("PATH", "")
        if bin_dir not in path.split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + path
            logger.info("Added managed Lima to PATH: %s", bin_dir)


def lima_status() -> dict[str, object]:
    """Check Lima installation status."""
    limactl = shutil.which("limactl")
    if limactl:
        return {"installed": True, "path": limactl, "managed": str(limactl) == str(_lima_bin())}
    return {"installed": False, "path": None, "managed": False}


# ---------------------------------------------------------------------------
# Lima install SSE stream
# ---------------------------------------------------------------------------


async def install_lima_stream():
    """SSE generator that downloads and installs Lima."""
    def sse(event: str, data: dict[str, object]) -> str:
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    bundled_tarball = _lima_offline_tarball_path()
    tmp_dir = tempfile.mkdtemp(prefix="hexagent_lima_")

    if bundled_tarball is not None:
        yield sse("progress", {"step": "extracting", "message": f"Installing Lima from bundled package ({bundled_tarball.name})..."})
        tarball_path = str(bundled_tarball)
    else:
        yield sse("progress", {"step": "resolving", "message": "Resolving latest Lima version..."})
        version = await _resolve_lima_version()
        yield sse("progress", {"step": "downloading", "message": f"Downloading Lima v{version}..."})
        tarball_path = os.path.join(tmp_dir, "lima.tar.gz")
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

    try:
        yield sse("progress", {"step": "extracting", "message": "Extracting..."})

        _lima_dir().mkdir(parents=True, exist_ok=True)

        def _extract() -> None:
            with tarfile.open(tarball_path, "r:gz") as tf:
                tf.extractall(path=str(_lima_dir()))  # noqa: S202

        await asyncio.to_thread(_extract)

        bin_dir = _lima_dir() / "bin"
        if bin_dir.is_dir():
            for f in bin_dir.iterdir():
                f.chmod(f.stat().st_mode | 0o755)

        if not _lima_bin().is_file():
            yield sse("error", {"message": "Installation failed: limactl binary not found after extraction"})
            return

        proc = await asyncio.create_subprocess_exec(
            "xattr", "-dr", "com.apple.quarantine", str(_lima_dir()),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

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

        ensure_managed_lima_on_path()
        label = bundled_tarball.stem if bundled_tarball is not None else f"v{version}"
        yield sse("done", {"message": f"Lima {label} installed successfully", "path": str(_lima_bin())})

    except Exception:
        logger.exception("Lima installation failed")
        yield sse("error", {"message": "Lima installation failed. Check server logs for details."})
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Lima VM shell / status helpers
# ---------------------------------------------------------------------------


async def lima_shell(cmd: str, *, timeout: float = 60) -> tuple[int, str, str]:
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


async def lima_instance_status() -> str | None:
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


# ---------------------------------------------------------------------------
# Entitlement helper
# ---------------------------------------------------------------------------


async def ensure_limactl_entitlement() -> None:
    """Verify limactl has the virtualization entitlement; re-sign if missing."""
    limactl = shutil.which("limactl")
    if not limactl:
        return

    proc = await asyncio.create_subprocess_exec(
        "codesign", "-d", "--entitlements", "-", "--xml", limactl,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    if b"com.apple.security.virtualization" in stdout:
        return

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


# ---------------------------------------------------------------------------
# Build manager — Lima implementation
# ---------------------------------------------------------------------------


async def _stream_stderr(mgr, proc: asyncio.subprocess.Process) -> str:
    """Read limactl stderr line-by-line and emit progress events."""
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
        if "Downloading" in text or "downloading" in text:
            mgr._emit("progress", {"step": "downloading", "message": text})
        elif "Waiting" in text or "Booting" in text:
            mgr._emit("progress", {"step": "booting", "message": text})
        elif "READY" in text or "ready" in text:
            mgr._emit("progress", {"step": "ready", "message": text})
        else:
            mgr._emit("progress", {"step": "output", "message": text})
    return last_line


async def _start_instance(mgr, *cmd: str) -> tuple[bool, str]:
    """Run a limactl start command and return (success, error_detail).

    Races stderr streaming vs status polling.  Whichever finishes first wins.
    DEVNULL for stdout avoids the pipe-buffer deadlock.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    mgr._process = proc

    async def _poll_running() -> None:
        for _ in range(60):  # up to 5 min (5 s × 60)
            await asyncio.sleep(5)
            if await lima_instance_status() == "Running":
                return

    stream_task = asyncio.create_task(_stream_stderr(mgr, proc))
    poll_task = asyncio.create_task(_poll_running())

    done_set, _ = await asyncio.wait(
        {stream_task, poll_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if poll_task in done_set:
        stream_task.cancel()
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return True, ""

    poll_task.cancel()
    last_line = ""
    try:
        last_line = stream_task.result()
    except Exception:
        pass
    await proc.wait()
    if proc.returncode == 0:
        return True, ""
    return False, last_line


def _macos_version() -> tuple[int, int]:
    """Return (major, minor) of the running macOS version."""
    ver = platform.mac_ver()[0]  # e.g. "12.6.1" or "13.0"
    parts = ver.split(".")
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return (0, 0)


def _patch_yaml_for_compat(text: str) -> str:
    """Replace VZ-specific settings with QEMU equivalents on macOS < 13.

    Apple Virtualization.framework (vmType: vz) requires macOS 13 Ventura or
    higher.  On macOS 12 Monterey and earlier, fall back to QEMU with 9p
    mounts, which are slower but broadly compatible.
    """
    major, _ = _macos_version()
    if major >= 13:
        return text
    text = re.sub(r'vmType:\s*"vz"', 'vmType: "qemu"', text)
    text = re.sub(r'mountType:\s*"virtiofs"', 'mountType: "9p"', text)
    return text


def _build_offline_yaml(yaml_path: Path, offline_image: Path, tmp_dir: str) -> Path:
    """Return a temporary YAML that prepends a local image to the images list."""
    arch = _resolve_arch()
    lima_arch = "aarch64" if arch == "arm64" else "x86_64"

    yaml_text = yaml_path.read_text(encoding="utf-8")
    local_entry = (
        f"  - location: \"file://{offline_image}\"\n"
        f"    arch: \"{lima_arch}\"\n"
    )
    modified = re.sub(
        r"^(images:\s*\n)",
        r"\1" + local_entry,
        yaml_text,
        flags=re.MULTILINE,
    )
    modified = _patch_yaml_for_compat(modified)

    tmp_yaml = os.path.join(tmp_dir, "hexagent.yaml")
    with open(tmp_yaml, "w", encoding="utf-8") as f:
        f.write(modified)
    return Path(tmp_yaml)


def _app_bundle_birthtime() -> float | None:
    """Return the macOS birthtime of the .app bundle, or None if unavailable.

    When running as a PyInstaller frozen binary the executable is at
    ``<Bundle>.app/Contents/MacOS/<binary>``.  We walk three levels up to
    reach the bundle root and read ``st_birthtime``.  Reinstalling the same
    DMG replaces the bundle and resets this timestamp, making it a reliable
    "was the app reinstalled?" signal.

    Returns None when not frozen (development) or if the path doesn't exist.
    """
    if not getattr(sys, "frozen", False):
        return None
    try:
        bundle = Path(sys.executable).resolve().parent.parent.parent
        if bundle.suffix != ".app":
            return None
        return bundle.stat().st_birthtime  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return None


_BIRTHTIME_MARKER = ".app-birthtime"


def _read_installed_birthtime(instance_dir: Path) -> float | None:
    """Read the stored app bundle birthtime from the Lima instance dir."""
    marker = instance_dir / _BIRTHTIME_MARKER
    if not marker.exists():
        return None
    try:
        return float(marker.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _write_installed_birthtime(instance_dir: Path, birthtime: float) -> None:
    """Persist the app bundle birthtime into the Lima instance dir."""
    (instance_dir / _BIRTHTIME_MARKER).write_text(str(birthtime), encoding="utf-8")


def _fixup_instance_lima_yaml(instance_dir: Path) -> None:
    """Patch lima.yaml to replace the original builder's paths with local paths.

    Handles two classes of stale paths:
    - The builder's LIMA_HOME (e.g. /Users/bxj/.lima) → current LIMA_HOME
    - The builder's home dir (e.g. /Users/bxj) → current home dir
    Also strips stale session mounts (mountPoint: /sessions/...) that are
    specific to the builder's active sessions.
    """
    meta_file = instance_dir / ".prebuilt-lima-home"
    if not meta_file.exists():
        return
    lima_yaml = instance_dir / "lima.yaml"
    if not lima_yaml.exists():
        return

    old_lima_home = meta_file.read_text(encoding="utf-8").strip()
    if not old_lima_home:
        return

    lima_home = Path(os.environ.get("LIMA_HOME", str(Path.home() / ".lima")))
    new_lima_home = str(lima_home)
    text = lima_yaml.read_text(encoding="utf-8")

    if old_lima_home != new_lima_home:
        text = text.replace(old_lima_home, new_lima_home)

    old_home = old_lima_home.removesuffix("/.lima")
    new_home = str(Path.home())
    if old_home and old_home != new_home and old_home != old_lima_home:
        text = text.replace(old_home, new_home)

    # Strip stale session mounts — developer-specific, meaningless on other machines.
    # Each mount block has multiple indented lines (location, mountPoint, writable, …);
    # use a lookahead to identify /sessions/ blocks then consume all their indented lines.
    text = re.sub(
        r"- location:[^\n]*\n(?=(?:[ \t]+[^\n]*\n)*[ \t]+mountPoint: /sessions/)(?:[ \t]+[^\n]*\n)+",
        "",
        text,
    )

    # Patch vmType/mountType for macOS < 13 (VZ requires macOS 13+).
    text = _patch_yaml_for_compat(text)

    lima_yaml.write_text(text, encoding="utf-8")


def _lima_ssh_port(lima_yaml_path: Path) -> int | None:
    """Parse the dynamic SSH port Lima assigned in its instance lima.yaml."""
    try:
        import re
        text = lima_yaml_path.read_text(encoding="utf-8")
        m = re.search(r"^\s*localPort\s*:\s*(\d+)", text, re.MULTILINE)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


async def _fix_prebuilt_boot_done() -> None:
    """Fix stale /run/lima-boot-done in a prebuilt-restored Lima instance.

    Prebuilt archives snapshot an old instance ID in /run/lima-boot-done.
    When restored, Lima generates a fresh IID for the new start but cloud-init
    won't re-run (it has already-ran markers on the old disk image), so the
    boot-done file never gets updated and Lima's boot check loops forever.

    Lima establishes an SSH ControlMaster socket early in the start sequence.
    Once that socket appears we piggyback on it to read the correct IID from
    /mnt/lima-cidata/meta-data (the cidata Lima freshly created) and write it
    to /run/lima-boot-done.  Lima's next poll of the file will pass and the
    instance will transition to Running normally.
    """
    lima_home = Path(os.environ.get("LIMA_HOME", str(Path.home() / ".lima")))
    ssh_sock = lima_home / _LIMA_INSTANCE / "ssh.sock"
    ssh_config = lima_home / _LIMA_INSTANCE / "ssh.config"

    # Wait for Lima's SSH ControlMaster socket to appear (up to ~3 min).
    for _ in range(36):
        await asyncio.sleep(5)
        if ssh_sock.exists():
            break
    else:
        logger.debug("[prebuilt] SSH socket never appeared, skipping boot-done fix")
        return

    # Brief pause so the ControlMaster session is fully stable.
    await asyncio.sleep(2)

    # Read the current IID from Lima-mounted cidata and write boot-done.
    fix_cmd = (
        "iid=$(awk '/^instance-id:/{print $2}' /mnt/lima-cidata/meta-data 2>/dev/null); "
        '[ -n "$iid" ] && printf \'%s\\n\' "$iid" | sudo tee /run/lima-boot-done > /dev/null'
    )
    # Build SSH args.  Lima generates ssh.config with the correct dynamic port
    # (e.g. 59069) and ControlMaster settings.  Using it avoids the port-mismatch
    # that caused the previous ControlMaster slave connection to be rejected when
    # the command connected to the default port 22 instead of Lima's actual port.
    if ssh_config.exists():
        ssh_args = ["ssh", "-F", str(ssh_config), f"lima-{_LIMA_INSTANCE}"]
    else:
        # Fallback: read port from lima.yaml if possible.
        identity = lima_home / "_config" / "user"
        port = _lima_ssh_port(lima_home / _LIMA_INSTANCE / "lima.yaml")
        ssh_args = [
            "ssh", "-F", "/dev/null",
            "-o", f"IdentityFile={identity}",
            "-o", f"ControlPath={ssh_sock}",
            "-o", "ControlMaster=no",
            "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "GSSAPIAuthentication=no",
            "-o", "User=hexagent",
            *(["-p", str(port)] if port else []),
            "127.0.0.1",
        ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_args,
            "--", "bash", "-c", fix_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            logger.info("[prebuilt] Lima boot-done marker fixed successfully")
        else:
            logger.debug(
                "[prebuilt] boot-done fix returned %d: %s",
                proc.returncode,
                (stderr or b"").decode("utf-8", errors="replace").strip(),
            )
    except Exception:
        logger.debug("[prebuilt] boot-done fix error", exc_info=True)


async def _restore_from_prebuilt(mgr, prebuilt: Path) -> None:
    """Restore a Lima instance from a prebuilt archive and start it."""
    global _vm_restored_from_prebuilt  # noqa: PLW0603

    size_mb = prebuilt.stat().st_size / (1024 * 1024)
    mgr._emit("progress", {"step": "creating", "message": f"Restoring bundled Lima VM image ({size_mb:.1f} MB)..."})

    lima_home = Path(os.environ.get("LIMA_HOME", str(Path.home() / ".lima")))
    instance_dir = lima_home / _LIMA_INSTANCE

    if instance_dir.exists():
        shutil.rmtree(instance_dir)
    lima_home.mkdir(parents=True, exist_ok=True)

    def _extract() -> None:
        with tarfile.open(str(prebuilt)) as tf:
            tf.extractall(str(lima_home))  # noqa: S202

    try:
        await asyncio.to_thread(_extract)
    except Exception as exc:
        mgr._emit("error", {"message": f"Failed to extract prebuilt image: {exc}"})
        mgr._status = "error"
        mgr._error = str(exc)
        return

    _fixup_instance_lima_yaml(instance_dir)
    birthtime = _app_bundle_birthtime()
    if birthtime is not None:
        _write_installed_birthtime(instance_dir, birthtime)

    mgr._emit("progress", {"step": "starting", "message": "Starting restored Lima VM..."})
    # Run a concurrent task that fixes the stale boot-done marker for older
    # prebuilt images where cloud-init won't re-run on a new Lima IID.
    boot_fix_task = asyncio.create_task(_fix_prebuilt_boot_done())
    ok, err = await _start_instance(mgr, "limactl", "start", _LIMA_INSTANCE, "--tty=false")
    boot_fix_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await boot_fix_task

    if ok:
        _vm_restored_from_prebuilt = True
        mgr._emit("done", {"message": "VM restored from bundled image and started successfully"})
        mgr._status = "done"
    else:
        mgr._emit("error", {"message": f"VM start failed after restore{' — ' + err if err else ''}"})
        mgr._status = "error"
        mgr._error = err


# ---------------------------------------------------------------------------
# Reinstall policy
# ---------------------------------------------------------------------------

# Set to True during active development to always rebuild the Lima instance
# from the prebuilt archive on every app start.  Set to False (default) once
# the VM image is stable — reinstall is then only triggered when the app bundle
# birthtime changes (i.e. the user dragged a new DMG into /Applications).
_FORCE_REINSTALL_ON_START: bool = False


async def _should_reinstall_from_prebuilt() -> bool:
    """Return True if the Lima instance should be rebuilt from the prebuilt archive.

    Two conditions can trigger a rebuild:
    - ``_FORCE_REINSTALL_ON_START`` is True (dev/unstable mode).
    - The app bundle birthtime changed, meaning the app was reinstalled
      (macOS resets birthtime on every install, even for the same DMG).

    Only active when running as a frozen PyInstaller binary with a prebuilt
    archive available.  Always returns False in dev mode (not frozen).
    """
    prebuilt = _lima_prebuilt_tar_path()
    if prebuilt is None:
        return False  # no prebuilt to restore from

    if _FORCE_REINSTALL_ON_START:
        logger.debug("[VM] _FORCE_REINSTALL_ON_START=True — will rebuild Lima instance")
        return True

    current = _app_bundle_birthtime()
    if current is None:
        return False  # dev mode — never force-reinstall
    lima_home = Path(os.environ.get("LIMA_HOME", str(Path.home() / ".lima")))
    stored = _read_installed_birthtime(lima_home / _LIMA_INSTANCE)
    return stored != current


async def teardown_lima_if_reinstalled() -> None:
    """Stop and delete the Lima instance if the app was reinstalled.

    Called once at backend startup (before any API requests).  If the app
    bundle birthtime changed (new DMG installed), the existing Lima instance
    is torn down so the frontend sees it as "not built" and triggers a fresh
    restore from the prebuilt archive.

    This runs synchronously at startup so that ``GET /api/setup/vm`` already
    returns the correct "not ready" state when the frontend first polls.
    """
    if sys.platform != "darwin":
        return
    if not await _should_reinstall_from_prebuilt():
        return

    logger.info("[VM] App reinstall detected at startup — tearing down Lima instance '%s'", _LIMA_INSTANCE)
    current_status = await lima_instance_status()

    if current_status == "Running":
        logger.info("[VM] Stopping Lima instance...")
        proc = await asyncio.create_subprocess_exec(
            "limactl", "stop", _LIMA_INSTANCE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    lima_home = Path(os.environ.get("LIMA_HOME", str(Path.home() / ".lima")))
    instance_dir = lima_home / _LIMA_INSTANCE
    if instance_dir.exists():
        logger.info("[VM] Deleting Lima instance directory: %s", instance_dir)
        shutil.rmtree(instance_dir)

    logger.info("[VM] Lima instance removed — will be rebuilt from prebuilt on next build trigger")


async def build_run_lima(mgr) -> None:
    """Drive _BuildManager for the Lima backend (macOS)."""
    await ensure_limactl_entitlement()

    instance_status = await lima_instance_status()

    if instance_status == "Running":
        mgr._emit("done", {"message": "VM is already running"})
        mgr._status = "done"
        return

    if instance_status == "Stopped":
        lima_home = Path(os.environ.get("LIMA_HOME", str(Path.home() / ".lima")))
        _fixup_instance_lima_yaml(lima_home / _LIMA_INSTANCE)
        mgr._emit("progress", {"step": "starting", "message": "Starting existing VM..."})
        # Prebuilt-based images may have a stale /run/lima-boot-done on disk —
        # run the fix concurrently here too, not only during the initial restore.
        boot_fix_task = asyncio.create_task(_fix_prebuilt_boot_done())
        ok, err = await _start_instance(mgr, "limactl", "start", _LIMA_INSTANCE, "--tty=false")
        boot_fix_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await boot_fix_task
        if ok:
            mgr._emit("done", {"message": "VM started successfully"})
            mgr._status = "done"
        else:
            mgr._emit("error", {"message": f"VM start failed{' — ' + err if err else ''}"})
            mgr._status = "error"
            mgr._error = err
        return

    yaml_path = vm_lima_dir() / "hexagent.yaml"
    if not yaml_path.is_file():
        mgr._emit("error", {"message": f"VM config not found: {yaml_path}"})
        mgr._status = "error"
        mgr._error = "Config not found"
        return

    # Option 1: restore from a prebuilt instance archive
    prebuilt = _lima_prebuilt_tar_path()
    if prebuilt is not None:
        logger.info("[VM] Option 1: restoring from prebuilt archive: %s", prebuilt)
        await _restore_from_prebuilt(mgr, prebuilt)
        return

    # Option 2: create VM using a local offline base image
    offline_image = _lima_offline_image_path()
    effective_yaml: str | Path = yaml_path
    tmp_yaml_dir: str | None = None

    if offline_image is not None:
        logger.info("[VM] Option 2: creating from bundled ubuntu image: %s", offline_image)
        mgr._emit("progress", {"step": "creating", "message": "Creating VM from bundled base image..."})
        try:
            tmp_yaml_dir = tempfile.mkdtemp(prefix="hexagent_lima_")
            effective_yaml = await asyncio.to_thread(
                _build_offline_yaml, yaml_path, offline_image, tmp_yaml_dir
            )
        except Exception as exc:
            logger.warning("Failed to build offline Lima YAML, falling back to online: %s", exc)
            effective_yaml = yaml_path
            if tmp_yaml_dir:
                shutil.rmtree(tmp_yaml_dir, ignore_errors=True)
                tmp_yaml_dir = None
    else:
        logger.info("[VM] Option 3: no offline assets found, downloading ubuntu image from internet")
        mgr._emit("progress", {"step": "creating", "message": "Creating VM (downloading base image)..."})
        # Apply compat patches (e.g. macOS 12 needs QEMU, not VZ) — option 2
        # already patches inside _build_offline_yaml; handle option 3 here.
        yaml_text = yaml_path.read_text(encoding="utf-8")
        patched_text = _patch_yaml_for_compat(yaml_text)
        if patched_text != yaml_text:
            tmp_yaml_dir = tempfile.mkdtemp(prefix="hexagent_lima_")
            compat_yaml = Path(tmp_yaml_dir) / "hexagent.yaml"
            compat_yaml.write_text(patched_text, encoding="utf-8")
            effective_yaml = compat_yaml

    # Option 3 (and fall-through from Option 2): start with YAML
    try:
        proc = await asyncio.create_subprocess_exec(
            "limactl", "start", f"--name={_LIMA_INSTANCE}", str(effective_yaml), "--tty=false",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        mgr._process = proc
        last_line = await _stream_stderr(mgr, proc)
        await proc.wait()
        if proc.returncode == 0:
            mgr._emit("done", {"message": "VM created successfully"})
            mgr._status = "done"
        else:
            detail = f" — {last_line}" if last_line else ""
            mgr._emit("error", {"message": f"VM creation failed (exit {proc.returncode}){detail}"})
            mgr._status = "error"
            mgr._error = f"exit {proc.returncode}"
    finally:
        if tmp_yaml_dir:
            shutil.rmtree(tmp_yaml_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Provision manager — Lima implementation
# ---------------------------------------------------------------------------

_SETUP_MARKER_DIRS = ("/var/lib/hexagent/setup", "/var/lib/openagent/setup")
_SETUP_VM_DIR = "/tmp/hexagent-setup"

import subprocess as _sp  # noqa: E402 (already imported above, reuse)


async def provision_run_lima(mgr, **kwargs: object) -> None:
    """Drive _ProvisionManager for the Lima backend (macOS)."""
    import subprocess as _subprocess

    force = bool(kwargs.get("force", False))

    instance_status = await lima_instance_status()
    if instance_status != "Running":
        mgr._emit("error", {"message": f"VM is not running (status: {instance_status})"})
        mgr._status = "error"
        mgr._error = "VM not running"
        return

    # Fast path: VM was restored from a prebuilt archive that already has
    # all dependencies baked in — skip provisioning entirely.
    # Also covers the case where the VM was already provisioned in a prior
    # session (check marker files via SSH with retries for SSH readiness).
    if not force:
        # If a prebuilt tar.gz is bundled with the app, the image already
        # contains all system dependencies — no provisioning needed regardless
        # of session state (handles app restarts where _vm_restored_from_prebuilt
        # is reset to False).
        should_skip = _vm_restored_from_prebuilt or (_lima_prebuilt_tar_path() is not None)
        if not should_skip:
            for _attempt in range(12):  # 12 × 5 s = 60 s
                rc_ssh, _, _ = await lima_shell("true", timeout=8)
                if rc_ssh == 0:
                    break
                logger.debug("[Provision] SSH not ready yet (attempt %d/12), retrying…", _attempt + 1)
                await asyncio.sleep(5)
            from hexagent_api.routes.setup import _PROVISION_STEPS
            last_step_id = _PROVISION_STEPS[-1][0]
            checks = " || ".join(
                f"test -f {d}/{last_step_id}.done" for d in _SETUP_MARKER_DIRS
            )
            rc_markers, _, _ = await lima_shell(checks, timeout=10)
            should_skip = rc_markers == 0

        if should_skip:
            from hexagent_api.routes.setup import _PROVISION_STEPS
            logger.info("[Provision] All setup markers present — skipping provisioning")
            for step_id, label in _PROVISION_STEPS:
                mgr._emit("step_skip", {"step": step_id, "message": label})
            mgr._emit("done", {"message": "VM already fully provisioned"})
            mgr._status = "done"
            return

    # Copy setup directory into VM
    mgr._emit("progress", {"step": "copying", "message": "Copying setup files to VM..."})
    setup_dir = vm_setup_lite_dir()
    if not setup_dir.is_dir():
        mgr._emit("error", {"message": f"Setup directory not found: {setup_dir}"})
        mgr._status = "error"
        mgr._error = "Setup dir not found"
        return

    with tempfile.TemporaryDirectory(prefix="hexagent_setup_") as tmp:
        tar_path = os.path.join(tmp, "setup.tar.gz")
        _subprocess.run(
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
            mgr._emit("error", {"message": "Failed to copy setup files to VM"})
            mgr._status = "error"
            mgr._error = "Copy failed"
            return

    rc, _, err = await lima_shell(
        f"sudo rm -rf {_SETUP_VM_DIR} && sudo mkdir -p {_SETUP_VM_DIR} && "
        f"sudo tar -xzf /tmp/hexagent-setup.tar.gz -C {_SETUP_VM_DIR} --strip-components=1 && "
        f"rm -f /tmp/hexagent-setup.tar.gz",
        timeout=30,
    )
    if rc != 0:
        mgr._emit("error", {"message": f"Failed to extract setup files in VM: {err}"})
        mgr._status = "error"
        mgr._error = "Extract failed"
        return

    mgr._emit("progress", {"step": "starting", "message": "Starting provisioning..."})

    cmd = f"sudo bash {_SETUP_VM_DIR}/setup.sh"
    if force:
        cmd += " --force"

    proc = await asyncio.create_subprocess_exec(
        "limactl", "shell", _LIMA_INSTANCE, "--", "bash", "-c", cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    mgr._process = proc

    assert proc.stdout is not None
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        if text.startswith("@@SETUP:"):
            mgr._handle_setup_line(text)

    await proc.wait()
    if proc.returncode == 0:
        mgr._emit("done", {"message": "Provisioning complete"})
        mgr._status = "done"
    else:
        mgr._emit("error", {"message": f"Provisioning failed (exit {proc.returncode})"})
        mgr._status = "error"
        mgr._error = f"exit {proc.returncode}"
