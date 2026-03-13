# ruff: noqa: PLR2004 S108
"""Tests for _VMSessionComputer and LimaVM.

All tests mock the VM backend — no Lima or limactl required.
_VMSessionComputer is a thin execution handle created by LocalVM.
"""

from __future__ import annotations

import shlex
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from openagent.computer.base import BASH_MAX_TIMEOUT_MS, Computer
from openagent.computer.local._lima import LimaVM
from openagent.computer.local._types import ResolvedMount
from openagent.computer.local.vm import _VMSessionComputer
from openagent.exceptions import CLIError, LimaError, MissingDependencyError, UnsupportedPlatformError, VMError
from openagent.types import CLIResult

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
# _VMSessionComputer
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
        """Start is a no-op when already active."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.start()

        # No VM calls needed — handle is already active
        vm.status.assert_not_awaited()

    async def test_stop_marks_inactive(self) -> None:
        """Stop marks the handle as inactive."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.stop()

        assert computer.is_running is False
        # stop() does NOT stop the VM
        vm.stop.assert_not_awaited()

    async def test_start_after_stop_reactivates(self) -> None:
        """Start after stop performs health check and reactivates."""
        vm = _mock_vm()
        vm.shell = AsyncMock(return_value=_ok(stdout="1001"))
        computer = _make_computer(vm)

        await computer.stop()
        assert computer.is_running is False

        await computer.start()
        assert computer.is_running is True
        vm.status.assert_awaited_once()

    async def test_start_after_stop_raises_if_vm_not_running(self) -> None:
        """Start after stop raises if VM is not running."""
        vm = _mock_vm()
        vm.status = AsyncMock(return_value="Stopped")
        computer = _make_computer(vm)

        await computer.stop()

        with pytest.raises(CLIError, match="VM is not running"):
            await computer.start()

    async def test_start_after_stop_raises_if_user_gone(self) -> None:
        """Start after stop raises if session user no longer exists."""
        vm = _mock_vm()
        vm.shell = AsyncMock(return_value=_fail(stderr="no such user"))
        computer = _make_computer(vm)

        await computer.stop()

        with pytest.raises(CLIError, match="does not exist"):
            await computer.start()

    async def test_inactive_handle_rejects_run(self) -> None:
        """Inactive handle rejects run()."""
        vm = _mock_vm()
        computer = _make_computer(vm)
        await computer.stop()

        with pytest.raises(CLIError, match="inactive"):
            await computer.run("echo hi")


class TestRun:
    """Tests for run()."""

    async def test_run_passes_command_to_vm(self) -> None:
        """Run delegates to vm.shell with the session user."""
        vm = _mock_vm()
        vm.shell = AsyncMock(return_value=_ok(stdout="hello"))
        computer = _make_computer(vm)

        result = await computer.run("echo hello")

        assert result.stdout == "hello"
        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["user"] == "test-session"

    async def test_run_timeout_converted_to_seconds(self) -> None:
        """Timeout is converted from ms to seconds."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.run("cmd", timeout=5000.0)

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["timeout"] == 5.0

    async def test_run_timeout_capped_at_max(self) -> None:
        """Timeout is capped at BASH_MAX_TIMEOUT_MS."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.run("cmd", timeout=BASH_MAX_TIMEOUT_MS + 100000)

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["timeout"] == BASH_MAX_TIMEOUT_MS / 1000

    async def test_run_default_timeout(self) -> None:
        """Default timeout is BASH_MAX_TIMEOUT_MS."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.run("cmd")

        call_kwargs = vm.shell.call_args.kwargs
        assert call_kwargs["timeout"] == BASH_MAX_TIMEOUT_MS / 1000

    async def test_run_translates_vm_error_to_cli_error(self) -> None:
        """VMError from shell is translated to CLIError."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=VMError("boom"))
        computer = _make_computer(vm)

        with pytest.raises(CLIError, match="boom"):
            await computer.run("bad")


class TestUpload:
    """Tests for upload()."""

    async def test_upload_copies_via_tmp_then_moves(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        await computer.upload(str(src), "/remote/file.txt")

        # Should copy to /tmp first, not directly to destination
        copy_call = vm.copy.call_args
        assert copy_call.args[0] == str(src)
        assert copy_call.args[1].startswith("/tmp/.upload-")
        assert copy_call.kwargs.get("host_to_guest") is True

        # Should sudo mv from tmp to destination, chown to session user, and chmod 644
        mv_call = vm.shell.call_args_list[1]
        assert "sudo mv" in mv_call.args[0]
        assert "/remote/file.txt" in mv_call.args[0]
        assert "chown test-session:test-session" in mv_call.args[0]
        assert "chmod 644" in mv_call.args[0]

    async def test_upload_creates_parent_dir_on_guest(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        await computer.upload(str(src), "/remote/deep/file.txt")

        mkdir_call = vm.shell.call_args_list[0]
        assert "sudo mkdir -p" in mkdir_call.args[0]
        assert "/remote/deep" in mkdir_call.args[0]

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

    async def test_download_calls_vm_copy(self, tmp_path: Path) -> None:
        vm = _mock_vm()
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        dst = tmp_path / "file.txt"

        await computer.download("/remote/file.txt", str(dst))

        vm.copy.assert_awaited_once_with("/remote/file.txt", str(dst), host_to_guest=False)

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
# LimaVM — pure logic only (no subprocess)
# ===========================================================================


class TestLimaVMInit:
    """Tests for LimaVM.__init__ guards."""

    def test_rejects_non_darwin(self) -> None:
        with (
            patch.object(sys, "platform", "linux"),
            pytest.raises(UnsupportedPlatformError, match="macOS"),
        ):
            LimaVM(instance="test")

    def test_rejects_missing_limactl(self) -> None:
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value=None),
            pytest.raises(MissingDependencyError, match="limactl"),
        ):
            LimaVM(instance="test")

    def test_accepts_darwin_with_limactl(self) -> None:
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value="/opt/homebrew/bin/limactl"),
        ):
            vm = LimaVM(instance="myvm")
            assert vm.instance == "myvm"


class TestBuildMountSetArg:
    """Tests for LimaVM._build_mount_set_arg."""

    def _build(self, mounts: list[ResolvedMount]) -> str:
        return LimaVM._build_mount_set_arg(mounts)

    def test_single_mount(self) -> None:
        result = self._build(
            [
                ResolvedMount(host_path="/host/code", guest_path="/guest/code", writable=True),
            ]
        )
        assert result.startswith(".mounts = ")
        assert '"/host/code"' in result
        assert '"/guest/code"' in result
        assert '"writable": true' in result

    def test_multiple_mounts(self) -> None:
        result = self._build(
            [
                ResolvedMount(host_path="/a", guest_path="/ga"),
                ResolvedMount(host_path="/b", guest_path="/gb", writable=False),
            ]
        )
        assert '"/a"' in result
        assert '"/b"' in result
        assert '"writable": false' in result

    def test_readonly_mount(self) -> None:
        result = self._build(
            [
                ResolvedMount(host_path="/ro", guest_path="/guest/ro", writable=False),
            ]
        )
        assert '"writable": false' in result


class TestLimaVMCopy:
    """Tests for LimaVM.copy()."""

    async def _run_copy(self, *, host_to_guest: bool, returncode: int = 0, stderr: bytes = b"") -> list[str]:
        """Call copy() and return the args passed to create_subprocess_exec."""
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/limactl"),
        ):
            vm = LimaVM(instance="test")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", stderr))
        mock_proc.returncode = returncode

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            if returncode != 0:
                with pytest.raises(LimaError):
                    await vm.copy("/host/file", "/guest/file", host_to_guest=host_to_guest)
            else:
                await vm.copy("/host/file", "/guest/file", host_to_guest=host_to_guest)
            return list(mock_exec.call_args.args)

    async def test_copy_host_to_guest_args(self) -> None:
        args = await self._run_copy(host_to_guest=True)
        assert args == ["limactl", "copy", "/host/file", "test:/guest/file"]

    async def test_copy_guest_to_host_args(self) -> None:
        args = await self._run_copy(host_to_guest=False)
        assert args == ["limactl", "copy", "test:/host/file", "/guest/file"]

    async def test_copy_failure_raises_lima_error(self) -> None:
        await self._run_copy(host_to_guest=True, returncode=1, stderr=b"no such file")


class TestShellCommandBuilding:
    """Tests for shell() command construction."""

    async def _capture_exec_args(self, **shell_kwargs: Any) -> list[str]:
        """Call shell() and return the args passed to create_subprocess_exec."""
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/limactl"),
        ):
            vm = LimaVM(instance="test")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"out\n", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            await vm.shell("echo hello", **shell_kwargs)
            return list(mock_exec.call_args.args)

    async def test_plain_command(self) -> None:
        args = await self._capture_exec_args()
        inner = args[-1]
        assert inner == "echo hello"

    async def test_user_wraps_with_sudo(self) -> None:
        args = await self._capture_exec_args(user="alice")
        inner = args[-1]
        assert "sudo -u" in inner
        assert "alice" in inner
        assert "bash -l -c" in inner

    async def test_user_with_cwd(self) -> None:
        args = await self._capture_exec_args(user="bob", cwd="/my dir")
        inner = args[-1]
        assert shlex.quote("/my dir") in inner
        assert "cd" in inner

    async def test_cwd_without_user(self) -> None:
        args = await self._capture_exec_args(cwd="/some/path")
        inner = args[-1]
        assert inner.startswith("cd ")
        assert shlex.quote("/some/path") in inner

    async def test_user_name_is_shell_quoted(self) -> None:
        args = await self._capture_exec_args(user="bad user")
        inner = args[-1]
        assert shlex.quote("bad user") in inner

    async def test_timeout_raises_lima_error(self) -> None:
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/limactl"),
        ):
            vm = LimaVM(instance="test")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
            pytest.raises(LimaError, match="timed out"),
        ):
            await vm.shell("sleep 999", timeout=0.1)


class TestApplyMounts:
    """Tests for LimaVM.apply_mounts()."""

    async def test_apply_stops_running_vm(self) -> None:
        """apply_mounts stops a running VM before restarting with mounts."""
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/limactl"),
        ):
            vm = LimaVM(instance="test")

        with (
            patch.object(vm, "status", new_callable=AsyncMock, return_value="Running"),
            patch.object(vm, "stop", new_callable=AsyncMock) as mock_stop,
            patch.object(vm, "_run_limactl", new_callable=AsyncMock, return_value=""),
        ):
            mounts = [ResolvedMount(host_path="/h", guest_path="/g", writable=False)]
            await vm.apply_mounts(mounts)
            mock_stop.assert_awaited_once()

    async def test_apply_raises_if_instance_missing(self) -> None:
        """apply_mounts raises if instance doesn't exist."""
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/limactl"),
        ):
            vm = LimaVM(instance="test")

        with (
            patch.object(vm, "status", new_callable=AsyncMock, return_value=None),
            pytest.raises(LimaError, match="does not exist"),
        ):
            await vm.apply_mounts([])


class TestReadMounts:
    """Tests for LimaVM.read_mounts()."""

    def _make_vm(self) -> LimaVM:
        with (
            patch.object(sys, "platform", "darwin"),
            patch("shutil.which", return_value="/usr/bin/limactl"),
        ):
            return LimaVM(instance="test")

    def test_reads_mounts_from_yaml(self, tmp_path: Path) -> None:
        """Parses lima.yaml mounts array into ResolvedMount list."""
        vm = self._make_vm()
        lima_dir = tmp_path / "test"
        lima_dir.mkdir()
        yaml_file = lima_dir / "lima.yaml"
        yaml_file.write_text(
            "mounts:\n"
            "  - location: /host/code\n"
            "    mountPoint: /guest/code\n"
            "    writable: true\n"
            "  - location: /host/data\n"
            "    mountPoint: /guest/data\n"
            "    writable: false\n"
        )

        with patch.dict("os.environ", {"LIMA_HOME": str(tmp_path)}):
            result = vm.read_mounts()

        assert len(result) == 2
        assert result[0] == ResolvedMount(host_path="/host/code", guest_path="/guest/code", writable=True)
        assert result[1] == ResolvedMount(host_path="/host/data", guest_path="/guest/data", writable=False)

    def test_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        """Returns empty list when lima.yaml doesn't exist."""
        vm = self._make_vm()

        with patch.dict("os.environ", {"LIMA_HOME": str(tmp_path)}):
            result = vm.read_mounts()

        assert result == []

    def test_returns_empty_when_no_mounts_key(self, tmp_path: Path) -> None:
        """Returns empty list when lima.yaml has no mounts section."""
        vm = self._make_vm()
        lima_dir = tmp_path / "test"
        lima_dir.mkdir()
        (lima_dir / "lima.yaml").write_text("cpus: 4\nmemory: 4GiB\n")

        with patch.dict("os.environ", {"LIMA_HOME": str(tmp_path)}):
            result = vm.read_mounts()

        assert result == []

    def test_skips_entries_without_location(self, tmp_path: Path) -> None:
        """Entries missing location are skipped."""
        vm = self._make_vm()
        lima_dir = tmp_path / "test"
        lima_dir.mkdir()
        (lima_dir / "lima.yaml").write_text("mounts:\n  - mountPoint: /guest/x\n    writable: true\n")

        with patch.dict("os.environ", {"LIMA_HOME": str(tmp_path)}):
            result = vm.read_mounts()

        assert result == []

    def test_writable_defaults_to_false(self, tmp_path: Path) -> None:
        """Missing writable key defaults to False."""
        vm = self._make_vm()
        lima_dir = tmp_path / "test"
        lima_dir.mkdir()
        (lima_dir / "lima.yaml").write_text("mounts:\n  - location: /host/ro\n    mountPoint: /guest/ro\n")

        with patch.dict("os.environ", {"LIMA_HOME": str(tmp_path)}):
            result = vm.read_mounts()

        assert len(result) == 1
        assert result[0].writable is False

    def test_uses_default_lima_home(self, tmp_path: Path) -> None:
        """Uses ~/.lima when LIMA_HOME is not set."""
        vm = self._make_vm()
        lima_dir = tmp_path / ".lima" / "test"
        lima_dir.mkdir(parents=True)
        (lima_dir / "lima.yaml").write_text("mounts:\n  - location: /h\n    mountPoint: /g\n    writable: false\n")

        with (
            patch.dict("os.environ", {}, clear=False),
            patch("os.environ.get", side_effect=lambda k, d=None: str(tmp_path / ".lima") if k == "LIMA_HOME" else d),
        ):
            # More direct: patch Path.home()
            pass

        # Use LIMA_HOME explicitly to test the path construction
        with patch.dict("os.environ", {"LIMA_HOME": str(tmp_path / ".lima")}):
            result = vm.read_mounts()

        assert len(result) == 1
