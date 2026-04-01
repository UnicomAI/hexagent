# ruff: noqa: PLR2004 S108 ARG005 UP012
"""Tests for WslVM and _VMSessionComputer (Windows variant).

All tests mock the WSL backend - no wsl.exe or WSL2 required.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from hexagent.computer.base import BASH_MAX_TIMEOUT_MS, Computer
from hexagent.computer.local._types import ResolvedMount
from hexagent.computer.local._wsl import (
    WslVM,
    _decode_wsl_output,
    _parse_status_output,
    _session_user_from_guest_mount_path,
    _win_path_to_wsl,
)
from hexagent.computer.local.vm_win import LocalVM, _VMSessionComputer
from hexagent.exceptions import CLIError, MissingDependencyError, UnsupportedPlatformError, VMError, WslError
from hexagent.types import CLIResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(stdout: str = "", stderr: str = "") -> CLIResult:
    """Build a successful CLIResult."""
    return CLIResult(stdout=stdout, stderr=stderr, exit_code=0)


def _fail(stderr: str = "", exit_code: int = 1) -> CLIResult:
    """Build a failed CLIResult."""
    return CLIResult(stdout="", stderr=stderr, exit_code=exit_code)


def _mock_vm() -> AsyncMock:
    """Create a mock VM backend with sensible defaults."""
    vm = AsyncMock()
    vm.start = AsyncMock()
    vm.stop = AsyncMock()
    vm.apply_mounts = AsyncMock()
    vm.shell = AsyncMock(return_value=_ok())
    vm.status = AsyncMock(return_value="Running")
    return vm


def _make_computer(vm: AsyncMock, session_name: str = "test-session") -> _VMSessionComputer:
    """Create a _VMSessionComputer with a mocked VM backend."""
    return _VMSessionComputer(vm=vm, session_name=session_name)


# ===========================================================================
# _VMSessionComputer (Windows variant)
# ===========================================================================


class TestProperties:
    """Tests for properties."""

    def test_is_running_true_by_default(self) -> None:
        computer = _make_computer(_mock_vm())
        assert computer.is_running is True

    def test_session_name_set(self) -> None:
        computer = _make_computer(_mock_vm(), session_name="my-session")
        assert computer.session_name == "my-session"


class TestStartStop:
    """Tests for start/stop."""

    async def test_start_noop_when_active(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.start()

        vm.status.assert_not_awaited()

    async def test_stop_marks_inactive(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.stop()

        assert computer.is_running is False
        vm.stop.assert_not_awaited()

    async def test_start_after_stop_reactivates(self) -> None:
        vm = _mock_vm()
        vm.shell = AsyncMock(return_value=_ok(stdout="1001"))
        computer = _make_computer(vm)

        await computer.stop()
        assert computer.is_running is False

        await computer.start()
        assert computer.is_running is True
        vm.status.assert_awaited_once()

    async def test_start_after_stop_raises_if_distro_not_running(self) -> None:
        vm = _mock_vm()
        vm.status = AsyncMock(return_value="Stopped")
        computer = _make_computer(vm)

        await computer.stop()

        with pytest.raises(CLIError, match="not running"):
            await computer.start()

    async def test_start_after_stop_raises_if_user_gone(self) -> None:
        vm = _mock_vm()
        vm.shell = AsyncMock(return_value=_fail(stderr="no such user"))
        computer = _make_computer(vm)

        await computer.stop()

        with pytest.raises(CLIError, match="does not exist"):
            await computer.start()

    async def test_inactive_handle_rejects_run(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)
        await computer.stop()

        with pytest.raises(CLIError, match="inactive"):
            await computer.run("echo hi")


class TestRun:
    """Tests for run()."""

    async def test_run_passes_command_to_vm(self) -> None:
        vm = _mock_vm()
        vm.shell = AsyncMock(return_value=_ok(stdout="hello"))
        computer = _make_computer(vm)

        result = await computer.run("echo hello")

        assert result.stdout == "hello"
        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["user"] == "test-session"

    async def test_run_timeout_converted_to_seconds(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.run("cmd", timeout=5000.0)

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["timeout"] == 5.0

    async def test_run_timeout_capped_at_max(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.run("cmd", timeout=BASH_MAX_TIMEOUT_MS + 100000)

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["timeout"] == BASH_MAX_TIMEOUT_MS / 1000

    async def test_run_default_timeout(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.run("cmd")

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["timeout"] == BASH_MAX_TIMEOUT_MS / 1000

    async def test_run_translates_vm_error_to_cli_error(self) -> None:
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=VMError("boom"))
        computer = _make_computer(vm)

        with pytest.raises(CLIError, match="boom"):
            await computer.run("bad")

    async def test_run_passes_default_cwd_to_vm_shell(self) -> None:
        vm = _mock_vm()
        computer = _VMSessionComputer(vm=vm, session_name="test-session", default_cwd="/sessions/test-session/mnt/code")

        await computer.run("pwd")

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["cwd"] == "/sessions/test-session/mnt/code"

    async def test_set_default_cwd_updates_future_run_calls(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)
        computer.set_default_cwd("/sessions/test-session/mnt/project")

        await computer.run("pwd")

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["cwd"] == "/sessions/test-session/mnt/project"


class TestLocalVMComputerDefaultCwd:
    """Tests for LocalVM.computer default working directory behavior."""

    async def test_new_session_defaults_to_session_home(self) -> None:
        backend = _mock_vm()
        vm = object.__new__(LocalVM)
        vm._vm = backend
        vm._instance = "openagent"
        vm._lock = asyncio.Lock()
        vm._generate_unique_name = AsyncMock(return_value="alice")  # type: ignore[method-assign]
        vm._create_user = AsyncMock()  # type: ignore[method-assign]

        computer = await LocalVM.computer(vm)
        await computer.run("pwd")

        call_kwargs = backend.shell.call_args.kwargs
        assert call_kwargs["user"] == "alice"
        assert call_kwargs["cwd"] == "/sessions/alice"


class TestUpload:
    """Tests for upload()."""

    async def test_upload_copies_via_tmp_then_moves(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        await computer.upload(str(src), "/remote/file.txt")

        copy_call = vm.copy.call_args
        assert copy_call.args[0] == str(src)
        assert copy_call.args[1].startswith("/tmp/.upload-")
        assert copy_call.kwargs.get("host_to_guest") is True

        mv_call = next(c for c in vm.shell.call_args_list if " mv " in c.args[0])
        assert "sudo mv" in mv_call.args[0]
        assert "/remote/file.txt" in mv_call.args[0]
        assert "chown test-session:test-session" in mv_call.args[0]
        assert "chmod 644" in mv_call.args[0]

    async def test_upload_uses_posix_parent_for_session_paths(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        await computer.upload(str(src), "/sessions/alice/mnt/uploads/file.txt")

        mkdir_call = next(c for c in vm.shell.call_args_list if "mkdir -p" in c.args[0])
        assert "/sessions/alice/mnt/uploads" in mkdir_call.args[0]
        assert "\\sessions\\alice\\mnt\\uploads" not in mkdir_call.args[0]

    async def test_upload_missing_src_raises_file_not_found(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        with pytest.raises(FileNotFoundError, match="Source file not found"):
            await computer.upload(str(tmp_path / "nope"), "/remote/file.txt")

    async def test_upload_src_is_dir_raises_cli_error(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        with pytest.raises(CLIError, match="not a file"):
            await computer.upload(str(tmp_path), "/remote/file.txt")

    async def test_upload_translates_vm_error_to_cli_error(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock(side_effect=VMError("copy failed"))
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        with pytest.raises(CLIError, match="copy failed"):
            await computer.upload(str(src), "/remote/file.txt")


class TestDownload:
    """Tests for download()."""

    async def test_download_stages_via_tmp(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        dst = tmp_path / "file.txt"

        await computer.download("/remote/file.txt", str(dst))

        # First shell call: sudo cp to tmp + chmod
        stage_call = next(c for c in vm.shell.call_args_list if " cp " in c.args[0])
        assert "sudo cp" in stage_call.args[0]
        assert "chmod 644" in stage_call.args[0]

        # Copy call uses the tmp path as source
        copy_call = vm.copy.call_args
        assert copy_call.args[0].startswith("/tmp/.download-")
        assert copy_call.args[1] == str(dst)
        assert copy_call.kwargs.get("host_to_guest") is False

    async def test_download_creates_parent_dirs_on_host(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        dst = tmp_path / "a" / "b" / "file.txt"

        await computer.download("/remote/file.txt", str(dst))

        assert dst.parent.exists()

    async def test_download_translates_vm_error_to_cli_error(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock(side_effect=VMError("copy failed"))
        computer = _make_computer(vm)

        with pytest.raises(CLIError, match="copy failed"):
            await computer.download("/remote/file.txt", str(tmp_path / "file.txt"))


class TestContextManager:
    """Tests for async context manager."""

    async def test_context_manager_starts_and_stops(self) -> None:
        vm = _mock_vm()
        computer = _make_computer(vm)

        async with computer:
            assert computer.is_running is True

        assert computer.is_running is False


class TestProtocolCompliance:
    """Tests for Computer protocol compliance."""

    def test_satisfies_computer_protocol(self) -> None:
        computer = _make_computer(_mock_vm())
        assert isinstance(computer, Computer)


# ===========================================================================
# WslVM - pure logic only (no subprocess)
# ===========================================================================


class TestWslVMInit:
    """Tests for WslVM.__init__ guards."""

    def test_rejects_non_win32(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "darwin"),
            pytest.raises(UnsupportedPlatformError, match="Windows"),
        ):
            WslVM(instance="test")

    def test_rejects_missing_wsl(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value=None),
            patch("pathlib.Path.is_file", return_value=False),
            pytest.raises(MissingDependencyError, match="wsl.exe"),
        ):
            WslVM(instance="test")

    def test_accepts_win32_with_wsl(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="myvm")
            assert vm.instance == "myvm"


# ===========================================================================
# WslVM start retry behavior
# ===========================================================================


class TestWslVMStart:
    """Tests for WslVM.start()."""

    def _make_vm(self) -> WslVM:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            return WslVM(instance="test")

    async def test_start_retries_once_on_transient_minus_one_exit(self) -> None:
        vm = self._make_vm()

        with (
            patch.object(vm, "status", new_callable=AsyncMock, return_value="Stopped"),
            patch.object(vm, "_run_wsl", new_callable=AsyncMock) as mock_run_wsl,
            patch.object(vm, "_apply_bind_mounts", new_callable=AsyncMock) as mock_apply,
        ):
            mock_run_wsl.side_effect = [
                WslError("wsl.exe failed (exit 4294967295): "),
                "ok",
            ]

            await vm.start()

            assert mock_run_wsl.await_count == 2
            mock_apply.assert_awaited_once()

    async def test_start_does_not_retry_on_non_transient_failure(self) -> None:
        vm = self._make_vm()

        with (
            patch.object(vm, "status", new_callable=AsyncMock, return_value="Stopped"),
            patch.object(vm, "_run_wsl", new_callable=AsyncMock, side_effect=WslError("wsl.exe failed (exit 1): boom")),
            patch.object(vm, "_apply_bind_mounts", new_callable=AsyncMock) as mock_apply,
            pytest.raises(WslError, match="exit 1"),
        ):
            await vm.start()

        mock_apply.assert_not_awaited()


# ===========================================================================
# WSL output decoding
# ===========================================================================


class TestDecodeWslOutput:
    """Tests for mixed-encoding stderr decoding."""

    def test_utf8_plain(self) -> None:
        assert _decode_wsl_output("hello".encode("utf-8")) == "hello"

    def test_utf16le_with_bom(self) -> None:
        raw = b"\xff\xfe" + "warning: test".encode("utf-16-le")
        assert "warning: test" in _decode_wsl_output(raw)

    def test_mixed_utf16le_prefix_and_utf8_tail(self) -> None:
        prefix = "wsl: localhost proxy config detected but not mirrored to WSL.\r\n".encode("utf-16-le")
        tail = b"/bin/bash: line 1: _mime_by_ext: command not found\n"
        text = _decode_wsl_output(prefix + tail)

        assert "localhost proxy config detected" in text
        assert "_mime_by_ext: command not found" in text


# ===========================================================================
# Status output parsing
# ===========================================================================


class TestStatusParsing:
    """Tests for _parse_status_output."""

    def test_utf8_output(self) -> None:
        output = ("  NAME          STATE           VERSION\n* Ubuntu        Running         2\n  hexagent     Stopped         2\n").encode("utf-8")

        entries = _parse_status_output(output)

        assert len(entries) == 2
        assert entries[0] == {"name": "Ubuntu", "state": "Running", "version": "2"}
        assert entries[1] == {"name": "hexagent", "state": "Stopped", "version": "2"}

    def test_utf16le_with_bom(self) -> None:
        text = "  NAME          STATE           VERSION\n  hexagent     Running         2\n"
        output = b"\xff\xfe" + text.encode("utf-16-le")

        entries = _parse_status_output(output)

        assert len(entries) == 1
        assert entries[0]["name"] == "hexagent"
        assert entries[0]["state"] == "Running"

    def test_default_distro_star_prefix(self) -> None:
        output = ("  NAME          STATE           VERSION\n* hexagent     Running         2\n").encode("utf-8")

        entries = _parse_status_output(output)

        assert len(entries) == 1
        assert entries[0]["name"] == "hexagent"

    def test_empty_output(self) -> None:
        entries = _parse_status_output(b"")
        assert entries == []

    def test_header_only(self) -> None:
        output = b"  NAME          STATE           VERSION\n"
        entries = _parse_status_output(output)
        assert entries == []

    def test_multiple_distros(self) -> None:
        output = (
            "  NAME          STATE           VERSION\n"
            "* Ubuntu        Running         2\n"
            "  Debian        Stopped         2\n"
            "  hexagent     Running         2\n"
        ).encode("utf-8")

        entries = _parse_status_output(output)

        assert len(entries) == 3
        names = [e["name"] for e in entries]
        assert names == ["Ubuntu", "Debian", "hexagent"]


# ===========================================================================
# Windows path conversion
# ===========================================================================


class TestWinPathToWsl:
    """Tests for _win_path_to_wsl."""

    def test_basic_backslash(self) -> None:
        assert _win_path_to_wsl(r"C:\Users\foo") == "/mnt/c/Users/foo"

    def test_basic_forward_slash(self) -> None:
        assert _win_path_to_wsl("C:/Users/foo") == "/mnt/c/Users/foo"

    def test_lowercase_drive(self) -> None:
        assert _win_path_to_wsl(r"c:\data") == "/mnt/c/data"

    def test_uppercase_drive_normalized(self) -> None:
        assert _win_path_to_wsl(r"D:\stuff") == "/mnt/d/stuff"

    def test_drive_root(self) -> None:
        assert _win_path_to_wsl("C:\\") == "/mnt/c/"

    def test_drive_only(self) -> None:
        # C: without trailing slash
        assert _win_path_to_wsl("C:") == "/mnt/c/"

    def test_rejects_unc_backslash(self) -> None:
        with pytest.raises(WslError, match="UNC"):
            _win_path_to_wsl(r"\\server\share")

    def test_rejects_unc_forward_slash(self) -> None:
        with pytest.raises(WslError, match="UNC"):
            _win_path_to_wsl("//server/share")

    def test_rejects_relative_path(self) -> None:
        with pytest.raises(WslError, match="drive letter"):
            _win_path_to_wsl("relative/path")


class TestSessionUserFromGuestMountPath:
    """Tests for _session_user_from_guest_mount_path."""

    def test_session_mnt_path(self) -> None:
        assert _session_user_from_guest_mount_path("/sessions/alice/mnt/work") == "alice"

    def test_trailing_slash(self) -> None:
        assert _session_user_from_guest_mount_path("/sessions/bob/mnt/x/") == "bob"

    def test_non_session_returns_none(self) -> None:
        assert _session_user_from_guest_mount_path("/mnt/code") is None
        assert _session_user_from_guest_mount_path("/sessions") is None


# ===========================================================================
# Mount config (JSON read/write)
# ===========================================================================


class TestReadWriteMounts:
    """Tests for read_mounts / write_mounts round-trip."""

    def _make_vm(self) -> WslVM:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            return WslVM(instance="test")

    def test_read_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        vm = self._make_vm()
        with patch.object(type(vm), "_config_path", new_callable=lambda: property(lambda self: tmp_path / "nope.json")):
            result = vm.read_mounts()
        assert result == []

    def test_round_trip(self, tmp_path: Path) -> None:
        vm = self._make_vm()
        config_dir = tmp_path / "test"
        config_dir.mkdir()
        config_path = config_dir / "mounts.json"

        with (
            patch.object(type(vm), "_config_dir", new_callable=lambda: property(lambda self: config_dir)),
            patch.object(type(vm), "_config_path", new_callable=lambda: property(lambda self: config_path)),
        ):
            mounts = [
                ResolvedMount(host_path=r"C:\Users\foo\code", guest_path="/mnt/code", writable=True),
                ResolvedMount(host_path=r"D:\data", guest_path="/sessions/alice/mnt/data", writable=False),
            ]
            vm.write_mounts(mounts)
            result = vm.read_mounts()

        assert len(result) == 2
        assert result[0] == mounts[0]
        assert result[1] == mounts[1]

    def test_write_creates_missing_config_dir(self, tmp_path: Path) -> None:
        vm = self._make_vm()
        missing_dir = tmp_path / "nonexistent"
        config_path = missing_dir / "mounts.json"

        with (
            patch.object(type(vm), "_config_dir", new_callable=lambda: property(lambda self: missing_dir)),
            patch.object(type(vm), "_config_path", new_callable=lambda: property(lambda self: config_path)),
        ):
            vm.write_mounts([ResolvedMount(host_path=r"C:\h", guest_path="/g", writable=False)])

        assert missing_dir.exists()
        assert config_path.exists()


# ===========================================================================
# Shell command building
# ===========================================================================


class TestShellCommandBuilding:
    """Tests for shell() command construction."""

    async def _capture_exec_args(self, **shell_kwargs: Any) -> list[str]:
        """Call shell() and return the args passed to create_subprocess_exec."""
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"out\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await vm.shell("echo hello", **shell_kwargs)
            return list(mock_exec.call_args.args)

    async def test_plain_command(self) -> None:
        args = await self._capture_exec_args()
        # wsl.exe -d test -- bash -c 'echo hello'
        assert args[0].lower().endswith("wsl.exe")
        assert "-d" in args
        assert "test" in args
        assert "--" in args
        assert "bash" in args
        assert "-c" in args
        assert args[-1] == "echo hello"

    async def test_user_adds_u_flag(self) -> None:
        args = await self._capture_exec_args(user="alice")
        assert "-u" in args
        alice_idx = args.index("-u") + 1
        assert args[alice_idx] == "alice"
        # Login shell flag should be present
        assert "-l" in args

    async def test_plain_command_no_login_shell(self) -> None:
        args = await self._capture_exec_args()
        # No -l for plain commands
        assert "-l" not in args

    async def test_user_with_cwd(self) -> None:
        args = await self._capture_exec_args(user="bob", cwd="/my dir")
        inner = args[-1]
        assert "cd" in inner
        assert "'/my dir'" in inner or '"/my dir"' in inner or "/my\\ dir" in inner

    async def test_cwd_without_user(self) -> None:
        args = await self._capture_exec_args(cwd="/some/path")
        inner = args[-1]
        assert inner.startswith("cd ")
        assert "/some/path" in inner

    async def test_timeout_raises_wsl_error(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(WslError, match="timed out"),
        ):
            await vm.shell("sleep 999", timeout=0.1)


# ===========================================================================
# Apply mounts
# ===========================================================================


class TestApplyMounts:
    """Tests for WslVM.apply_mounts()."""

    async def test_apply_stops_running_distro(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        with (
            patch.object(vm, "status", new_callable=AsyncMock, return_value="Running"),
            patch.object(vm, "_apply_bind_mounts", new_callable=AsyncMock) as mock_apply,
            patch.object(vm, "write_mounts"),
        ):
            mounts = [ResolvedMount(host_path=r"C:\h", guest_path="/g", writable=False)]
            await vm.apply_mounts(mounts)
            mock_apply.assert_awaited_once()

    async def test_apply_raises_if_instance_missing(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        with (
            patch.object(vm, "status", new_callable=AsyncMock, return_value=None),
            pytest.raises(WslError, match="does not exist"),
        ):
            await vm.apply_mounts([])


# ===========================================================================
# Apply bind mounts
# ===========================================================================


class TestApplyBindMounts:
    """Tests for _apply_bind_mounts (internal)."""

    async def test_applies_bind_mounts(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        mounts = [
            ResolvedMount(host_path=r"C:\Users\foo\code", guest_path="/mnt/code", writable=True),
            ResolvedMount(host_path=r"D:\data", guest_path="/mnt/data", writable=False),
        ]

        with (
            patch.object(vm, "read_mounts", return_value=mounts),
            patch.object(vm, "shell", new_callable=AsyncMock) as mock_shell,
        ):

            async def _shell_side_effect(command: str, *_: Any, **__: Any) -> CLIResult:  # noqa: PLR0911
                if command.startswith("wslpath -u"):
                    if "C:\\Users\\foo\\code" in command:
                        return _ok(stdout="/mnt/c/Users/foo/code")
                    if "D:\\data" in command:
                        return _ok(stdout="/mnt/d/data")
                if command == "mountpoint -q /mnt/code":
                    return _fail()
                if command == "mountpoint -q /mnt/data":
                    return _fail()
                if command.startswith("findmnt -n "):
                    return _ok(stdout="/dev/mock")
                if command.startswith(("ls -A /mnt/code | head -n 5", "ls -A /mnt/data | head -n 5")):
                    return _ok(stdout="ok")
                return _ok()

            mock_shell.side_effect = _shell_side_effect

            await vm._apply_bind_mounts()

            mount_calls = [c.args[0] for c in mock_shell.call_args_list if "mount --bind" in c.args[0]]
            assert len(mount_calls) == 2
            # Check writable mount (no remount)
            mount_call_1 = mount_calls[0]
            assert "mount --bind" in mount_call_1
            assert "/mnt/c/Users/foo/code" in mount_call_1
            assert "remount,ro" not in mount_call_1
            # Check read-only mount (remount ro)
            mount_call_2 = mount_calls[1]
            assert "mount --bind" in mount_call_2
            assert "remount,ro" in mount_call_2

    async def test_chown_after_writable_session_bind(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        mounts = [
            ResolvedMount(host_path=r"D:\w", guest_path="/sessions/alice/mnt/work", writable=True),
        ]

        with (
            patch.object(vm, "read_mounts", return_value=mounts),
            patch.object(vm, "shell", new_callable=AsyncMock) as mock_shell,
        ):

            async def _shell_side_effect(command: str, *_: Any, **__: Any) -> CLIResult:
                if command.startswith("wslpath -u") and "D:\\w" in command:
                    return _ok(stdout="/mnt/d/w")
                if command == "mountpoint -q /sessions/alice/mnt/work":
                    return _fail()
                if command.startswith("findmnt -n "):
                    return _ok(stdout="/dev/mock")
                if command.startswith("ls -A /sessions/alice/mnt/work | head -n 5"):
                    return _ok(stdout="ok")
                return _ok()

            mock_shell.side_effect = _shell_side_effect

            await vm._apply_bind_mounts()

            chown_call = next(c.args[0] for c in mock_shell.call_args_list if "chown -R" in c.args[0])
            assert "chown -R" in chown_call
            assert "alice:alice" in chown_call
            assert "/sessions/alice/mnt/work" in chown_call

    async def test_skips_already_mounted(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        mounts = [
            ResolvedMount(host_path=r"C:\code", guest_path="/mnt/code", writable=True),
        ]

        with (
            patch.object(vm, "read_mounts", return_value=mounts),
            patch.object(vm, "shell", new_callable=AsyncMock) as mock_shell,
        ):

            async def _shell_side_effect(command: str, *_: Any, **__: Any) -> CLIResult:
                if command.startswith("wslpath -u") and "C:\\code" in command:
                    return _ok(stdout="/mnt/c/code")
                if command == "mountpoint -q /mnt/code":
                    return _ok()
                if command == "ls -A /mnt/code":
                    return _ok(stdout="existing-file")
                return _ok()

            mock_shell.side_effect = _shell_side_effect

            await vm._apply_bind_mounts()

            # When already mounted and non-empty, bind step is skipped.
            assert not any("mount --bind" in c.args[0] for c in mock_shell.call_args_list)

    async def test_empty_mounts_is_noop(self) -> None:
        with (
            patch("hexagent.computer.local._wsl._PLATFORM", "win32"),
            patch("shutil.which", return_value="C:\\Windows\\System32\\wsl.exe"),
        ):
            vm = WslVM(instance="test")

        with (
            patch.object(vm, "read_mounts", return_value=[]),
            patch.object(vm, "shell", new_callable=AsyncMock) as mock_shell,
        ):
            await vm._apply_bind_mounts()
            mock_shell.assert_not_awaited()
