# ruff: noqa: ANN401, PLR2004, S108
"""Tests for LocalVMComputer.

All tests mock the VM backend — no Lima or limactl required.
"""

from __future__ import annotations

import shlex
import sys
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from openagent.computer.base import BASH_MAX_TIMEOUT_MS, SESSION_DIRS, Computer
from openagent.computer.local._lima import LimaVM, Mount
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
    # Default: shell succeeds with empty output
    vm.shell = AsyncMock(return_value=_ok())
    return vm


def _make_computer(
    vm: AsyncMock,
    *,
    resume: str | None = None,
    mounts: list[str] | None = None,
) -> Any:
    """Create a LocalVMComputer with a mocked VM backend."""
    with patch("openagent.computer.local.vm._create_vm", return_value=vm):
        from openagent.computer.local.vm import LocalVMComputer

        return LocalVMComputer(resume=resume, mounts=mounts)


# ===========================================================================
# LocalVMComputer
# ===========================================================================


class TestInit:
    """Tests for constructor validation."""

    def test_rejects_resume_with_mounts(self) -> None:
        """Cannot specify both resume and mounts."""
        vm = _mock_vm()
        with pytest.raises(ValueError, match="Cannot specify 'mounts'"):
            _make_computer(vm, resume="existing", mounts=["/tmp"])

    def test_rejects_nonexistent_mount_path(self, tmp_path: Path) -> None:
        """Mount path must exist."""
        vm = _mock_vm()
        with pytest.raises(ValueError, match="does not exist"):
            _make_computer(vm, mounts=[str(tmp_path / "nope")])

    def test_rejects_file_as_mount_path(self, tmp_path: Path) -> None:
        """Mount path must be a directory."""
        f = tmp_path / "file.txt"
        f.write_text("x")
        vm = _mock_vm()
        with pytest.raises(ValueError, match="not a directory"):
            _make_computer(vm, mounts=[str(f)])

    def test_valid_mount_paths_accepted(self, tmp_path: Path) -> None:
        """Valid directory mounts are accepted."""
        vm = _mock_vm()
        computer = _make_computer(vm, mounts=[str(tmp_path)])
        assert computer._mounts == [str(tmp_path)]


class TestProperties:
    """Tests for properties."""

    def test_is_running_false_before_start(self) -> None:
        computer = _make_computer(_mock_vm())
        assert computer.is_running is False

    def test_session_name_none_before_start(self) -> None:
        computer = _make_computer(_mock_vm())
        assert computer.session_name is None


class TestStartStop:
    """Tests for start/stop state machine."""

    async def test_start_creates_session(self) -> None:
        """First start creates a user via shell commands."""
        vm = _mock_vm()
        # id -u check fails (user doesn't exist) → name is unique
        # useradd succeeds, mkdir succeeds
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        computer = _make_computer(vm)

        await computer.start()

        assert computer.is_running is True
        assert computer.session_name is not None
        vm.start.assert_awaited_once()

    async def test_start_is_idempotent(self) -> None:
        """Calling start() twice doesn't re-initialize."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        computer = _make_computer(vm)

        await computer.start()
        await computer.start()  # no-op

        # VM start called once, shell called 3x (id + useradd + mkdir)
        vm.start.assert_awaited_once()
        assert vm.shell.await_count == 3

    async def test_stop_sets_not_running(self) -> None:
        """Stop marks the computer as not running."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        computer = _make_computer(vm)

        await computer.start()
        await computer.stop()

        assert computer.is_running is False
        vm.stop.assert_awaited_once()

    async def test_stop_is_noop_when_not_started(self) -> None:
        """Stop before start does nothing."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.stop()  # no-op, no error

        vm.stop.assert_not_awaited()

    async def test_restart_after_stop_calls_vm_start(self) -> None:
        """Second start() after stop() restarts the VM without re-creating user."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        computer = _make_computer(vm)

        await computer.start()
        name = computer.session_name
        await computer.stop()
        await computer.start()  # restart

        # VM.start called twice: initial + restart
        assert vm.start.await_count == 2
        # Session name preserved
        assert computer.session_name == name
        assert computer.is_running is True


class TestResume:
    """Tests for resuming an existing session."""

    async def test_resume_existing_session(self) -> None:
        """Resume sets session_name to the provided name."""
        vm = _mock_vm()
        # id -u succeeds → user exists
        vm.shell = AsyncMock(return_value=_ok(stdout="1001"))
        computer = _make_computer(vm, resume="my-session")

        await computer.start()

        assert computer.session_name == "my-session"

    async def test_resume_nonexistent_session_raises(self) -> None:
        """Resume raises VMError if user doesn't exist."""
        vm = _mock_vm()
        vm.shell = AsyncMock(return_value=_fail(stderr="no such user"))
        computer = _make_computer(vm, resume="ghost")

        with pytest.raises(VMError, match="does not exist"):
            await computer.start()


class TestRun:
    """Tests for run()."""

    async def test_run_passes_command_to_vm(self) -> None:
        """Run delegates to vm.shell with the session user."""
        vm = _mock_vm()
        # start: id -u fails (unique), useradd succeeds, mkdir succeeds
        # run: shell returns output
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok(stdout="hello")])
        computer = _make_computer(vm)
        await computer.start()

        result = await computer.run("echo hello")

        assert result.stdout == "hello"
        # Fourth call is the actual run
        call_kwargs = vm.shell.call_args_list[3].kwargs
        assert call_kwargs["user"] == computer.session_name

    async def test_run_auto_starts(self) -> None:
        """Run auto-starts if not started."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok(stdout="hi")])
        computer = _make_computer(vm)

        result = await computer.run("echo hi")

        assert computer.is_running is True
        assert result.stdout == "hi"

    async def test_run_timeout_converted_to_seconds(self) -> None:
        """Timeout is converted from ms to seconds."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])
        computer = _make_computer(vm)
        await computer.start()

        await computer.run("cmd", timeout=5000.0)

        call_kwargs = vm.shell.call_args_list[3].kwargs
        assert call_kwargs["timeout"] == 5.0

    async def test_run_timeout_capped_at_max(self) -> None:
        """Timeout is capped at BASH_MAX_TIMEOUT_MS."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])
        computer = _make_computer(vm)
        await computer.start()

        await computer.run("cmd", timeout=BASH_MAX_TIMEOUT_MS + 100000)

        call_kwargs = vm.shell.call_args_list[3].kwargs
        assert call_kwargs["timeout"] == BASH_MAX_TIMEOUT_MS / 1000

    async def test_run_default_timeout(self) -> None:
        """Default timeout is BASH_MAX_TIMEOUT_MS."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])
        computer = _make_computer(vm)
        await computer.start()

        await computer.run("cmd")

        call_kwargs = vm.shell.call_args_list[3].kwargs
        assert call_kwargs["timeout"] == BASH_MAX_TIMEOUT_MS / 1000

    async def test_run_translates_vm_error_to_cli_error(self) -> None:
        """VMError from shell is translated to CLIError."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), VMError("boom")])
        computer = _make_computer(vm)
        await computer.start()

        with pytest.raises(CLIError, match="boom"):
            await computer.run("bad")


class TestCreateUser:
    """Tests for _create_user directory setup."""

    async def test_creates_session_dirs(self) -> None:
        """Session directories from SESSION_DIRS are created after user creation."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        computer = _make_computer(vm)
        await computer.start()

        # Third shell call is the mkdir + chown
        mkdir_call = vm.shell.call_args_list[2].args[0]
        name = computer.session_name
        home = f"/sessions/{name}"
        for d in SESSION_DIRS:
            assert f"{home}/{d}" in mkdir_call

    async def test_mkdir_failure_raises_vm_error(self) -> None:
        """VMError raised when mkdir fails."""
        vm = _mock_vm()
        # id -u fails (unique), useradd succeeds, mkdir fails
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _fail(stderr="permission denied")])
        computer = _make_computer(vm)

        with pytest.raises(VMError, match="Failed to create session directories"):
            await computer.start()


class TestNameGeneration:
    """Tests for _generate_unique_name."""

    async def test_first_name_is_unique(self) -> None:
        """Returns first petname when it doesn't collide."""
        vm = _mock_vm()
        # id -u fails → name is unique
        vm.shell = AsyncMock(return_value=_fail())
        computer = _make_computer(vm)

        name = await computer._generate_unique_name()

        assert isinstance(name, str)
        assert len(name) > 0

    async def test_retries_on_collision(self) -> None:
        """Retries when name collides with existing user."""
        vm = _mock_vm()
        # First two names collide (id -u succeeds), third is unique
        vm.shell = AsyncMock(side_effect=[_ok(), _ok(), _fail()])
        computer = _make_computer(vm)

        name = await computer._generate_unique_name()

        assert isinstance(name, str)
        assert vm.shell.await_count == 3

    async def test_raises_after_max_attempts(self) -> None:
        """Raises VMError after exhausting all attempts."""
        vm = _mock_vm()
        # All names collide
        vm.shell = AsyncMock(return_value=_ok())
        computer = _make_computer(vm)

        with pytest.raises(VMError, match="Failed to generate"):
            await computer._generate_unique_name(max_attempts=3)

        assert vm.shell.await_count == 3


class TestDeleteSession:
    """Tests for delete_session."""

    async def test_delete_clears_state(self) -> None:
        """Delete resets session state."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])
        computer = _make_computer(vm)
        await computer.start()
        assert computer.session_name is not None

        await computer.delete_session()

        assert computer.session_name is None
        assert computer.is_running is False
        assert computer._session_initialized is False

    async def test_delete_calls_userdel(self) -> None:
        """Delete runs userdel -r on the VM."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])
        computer = _make_computer(vm)
        await computer.start()
        name = computer.session_name

        await computer.delete_session()

        # Last shell call is the userdel
        last_call = vm.shell.call_args_list[-1]
        assert f"userdel -r {name}" in last_call.args[0]

    async def test_delete_noop_without_session(self) -> None:
        """Delete before start is a no-op."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        await computer.delete_session()  # no error

        vm.shell.assert_not_awaited()


class TestListSessions:
    """Tests for list_sessions."""

    async def test_list_requires_running(self) -> None:
        """Raises VMError when not started."""
        vm = _mock_vm()
        computer = _make_computer(vm)

        with pytest.raises(VMError, match="not running"):
            await computer.list_sessions()

    async def test_list_returns_session_names(self) -> None:
        """Returns parsed session names from ls output."""
        vm = _mock_vm()
        vm.shell = AsyncMock(
            side_effect=[
                _fail(),
                _ok(),
                _ok(),  # start (id + useradd + mkdir)
                _ok(stdout="alpha bravo charlie"),  # ls
            ]
        )
        computer = _make_computer(vm)
        await computer.start()

        result = await computer.list_sessions()

        assert result == ["alpha", "bravo", "charlie"]

    async def test_list_returns_empty_on_failure(self) -> None:
        """Returns empty list when ls fails."""
        vm = _mock_vm()
        vm.shell = AsyncMock(
            side_effect=[
                _fail(),
                _ok(),
                _ok(),  # start
                _fail(),  # ls fails
            ]
        )
        computer = _make_computer(vm)
        await computer.start()

        assert await computer.list_sessions() == []

    async def test_list_returns_empty_on_no_output(self) -> None:
        """Returns empty list when /sessions/ is empty."""
        vm = _mock_vm()
        vm.shell = AsyncMock(
            side_effect=[
                _fail(),
                _ok(),
                _ok(),  # start
                _ok(stdout="   "),  # ls returns whitespace only
            ]
        )
        computer = _make_computer(vm)
        await computer.start()

        assert await computer.list_sessions() == []


class TestUpload:
    """Tests for upload()."""

    async def test_upload_calls_vm_copy(self, tmp_path: Path) -> None:
        """Upload calls vm.copy with host_to_guest=True."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok(), _ok()])
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        await computer.upload(str(src), "/remote/file.txt")

        vm.copy.assert_awaited_once_with(str(src), "/remote/file.txt", host_to_guest=True)

    async def test_upload_creates_parent_dir_on_guest(self, tmp_path: Path) -> None:
        """Upload runs mkdir -p on the guest before copying."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok(), _ok()])
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        await computer.upload(str(src), "/remote/deep/file.txt")

        # Fourth shell call (after id + useradd + mkdir) should be mkdir -p
        mkdir_call = vm.shell.call_args_list[3]
        assert "mkdir -p" in mkdir_call.args[0]
        assert "/remote/deep" in mkdir_call.args[0]

    async def test_upload_chowns_to_session_user(self, tmp_path: Path) -> None:
        """Upload chowns the file to the session user after copy."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok(), _ok()])
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        await computer.upload(str(src), "/remote/file.txt")

        # Fifth shell call should be chown
        chown_call = vm.shell.call_args_list[4]
        assert "chown" in chown_call.args[0]
        assert computer.session_name in chown_call.args[0]

    async def test_upload_auto_starts(self, tmp_path: Path) -> None:
        """Upload auto-starts if not running."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok(), _ok()])
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        assert not computer.is_running
        await computer.upload(str(src), "/remote/file.txt")
        assert computer.is_running

    async def test_upload_missing_src_raises_file_not_found(self, tmp_path: Path) -> None:
        """FileNotFoundError for missing source."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        computer = _make_computer(vm)
        await computer.start()

        with pytest.raises(FileNotFoundError, match="Source file not found"):
            await computer.upload(str(tmp_path / "nope"), "/remote/file.txt")

    async def test_upload_translates_vm_error_to_cli_error(self, tmp_path: Path) -> None:
        """VMError from copy is translated to CLIError."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])
        vm.copy = AsyncMock(side_effect=VMError("copy failed"))
        computer = _make_computer(vm)

        src = tmp_path / "file.txt"
        src.write_text("data")

        with pytest.raises(CLIError, match="copy failed"):
            await computer.upload(str(src), "/remote/file.txt")


class TestDownload:
    """Tests for download()."""

    async def test_download_calls_vm_copy(self, tmp_path: Path) -> None:
        """Download calls vm.copy with host_to_guest=False."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        dst = tmp_path / "file.txt"

        await computer.download("/remote/file.txt", str(dst))

        vm.copy.assert_awaited_once_with("/remote/file.txt", str(dst), host_to_guest=False)

    async def test_download_creates_parent_dirs_on_host(self, tmp_path: Path) -> None:
        """Download creates parent directories on host side."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        dst = tmp_path / "a" / "b" / "file.txt"

        await computer.download("/remote/file.txt", str(dst))

        assert dst.parent.exists()

    async def test_download_auto_starts(self, tmp_path: Path) -> None:
        """Download auto-starts if not running."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        vm.copy = AsyncMock()
        computer = _make_computer(vm)

        assert not computer.is_running
        await computer.download("/remote/file.txt", str(tmp_path / "file.txt"))
        assert computer.is_running

    async def test_download_translates_vm_error_to_cli_error(self, tmp_path: Path) -> None:
        """VMError from copy is translated to CLIError."""
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
        vm.copy = AsyncMock(side_effect=VMError("copy failed"))
        computer = _make_computer(vm)

        with pytest.raises(CLIError, match="copy failed"):
            await computer.download("/remote/file.txt", str(tmp_path / "file.txt"))


class TestContextManager:
    """Tests for async context manager."""

    async def test_context_manager_starts_and_stops(self) -> None:
        vm = _mock_vm()
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])
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

    def _build(self, mounts: list[Mount]) -> str:
        return LimaVM._build_mount_set_arg(mounts)

    def test_single_mount(self) -> None:
        result = self._build(
            [
                Mount(location="/host/code", mount_point="/guest/code", writable=True),
            ]
        )
        assert result.startswith(".mounts += ")
        assert '"/host/code"' in result
        assert '"/guest/code"' in result
        assert '"writable": true' in result

    def test_multiple_mounts(self) -> None:
        result = self._build(
            [
                Mount(location="/a", mount_point="/ga"),
                Mount(location="/b", mount_point="/gb", writable=False),
            ]
        )
        assert '"/a"' in result
        assert '"/b"' in result
        assert '"writable": false' in result

    def test_readonly_mount(self) -> None:
        result = self._build(
            [
                Mount(location="/ro", mount_point="/guest/ro", writable=False),
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
        """Host-to-guest passes src and instance:dst."""
        args = await self._run_copy(host_to_guest=True)
        assert args == ["limactl", "copy", "/host/file", "test:/guest/file"]

    async def test_copy_guest_to_host_args(self) -> None:
        """Guest-to-host passes instance:src and dst."""
        args = await self._run_copy(host_to_guest=False)
        assert args == ["limactl", "copy", "test:/host/file", "/guest/file"]

    async def test_copy_failure_raises_lima_error(self) -> None:
        """Non-zero exit code raises LimaError."""
        await self._run_copy(host_to_guest=True, returncode=1, stderr=b"no such file")


class TestShellCommandBuilding:
    """Tests for shell() command construction.

    We mock create_subprocess_exec to capture the args passed to it,
    verifying the command string is built correctly with proper escaping.
    """

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
        """No user/cwd — command passed directly."""
        args = await self._capture_exec_args()
        inner = args[-1]  # last arg is the bash -c <inner>
        assert inner == "echo hello"

    async def test_user_wraps_with_sudo(self) -> None:
        """User triggers sudo -u wrapper."""
        args = await self._capture_exec_args(user="alice")
        inner = args[-1]
        assert "sudo -u" in inner
        assert "alice" in inner
        assert "bash -l -c" in inner

    async def test_user_with_cwd(self) -> None:
        """User + cwd produces cd <quoted-cwd> in sudo wrapper."""
        args = await self._capture_exec_args(user="bob", cwd="/my dir")
        inner = args[-1]
        assert shlex.quote("/my dir") in inner
        assert "cd" in inner

    async def test_cwd_without_user(self) -> None:
        """Cwd without user prepends cd to command."""
        args = await self._capture_exec_args(cwd="/some/path")
        inner = args[-1]
        assert inner.startswith("cd ")
        assert shlex.quote("/some/path") in inner

    async def test_user_name_is_shell_quoted(self) -> None:
        """User name with special chars is properly quoted."""
        args = await self._capture_exec_args(user="bad user")
        inner = args[-1]
        # shlex.quote("bad user") → "'bad user'"
        assert shlex.quote("bad user") in inner

    async def test_timeout_raises_lima_error(self) -> None:
        """Timeout raises LimaError."""
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
