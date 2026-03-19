# ruff: noqa: ANN401, PLR2004, S108, ERA001
"""Tests for LocalVM (Windows variant).

All tests mock the WslVM backend — no WSL2 or wsl.exe required.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from openagent.computer.base import SESSION_DIRS, Mount
from openagent.computer.local._types import ResolvedMount
from openagent.computer.local.vm_win import LocalVM, _VMSessionComputer
from openagent.exceptions import VMError, VMMountConflictError
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


def _mock_vm(*, status: str = "Running") -> AsyncMock:
    """Create a mock VM backend with sensible defaults."""
    vm = AsyncMock()
    vm.start = AsyncMock()
    vm.stop = AsyncMock()
    vm.apply_mounts = AsyncMock()
    vm.shell = AsyncMock(return_value=_ok())
    vm.status = AsyncMock(return_value=status)
    vm.read_mounts = list  # sync, returns empty by default
    vm.write_mounts = Mock()  # sync
    return vm


def _make_manager(vm: AsyncMock) -> Any:
    """Create a LocalVM (Windows) with a mocked VM backend."""
    with patch("openagent.computer.local.vm_win.LocalVM.__init__", return_value=None):
        mgr = LocalVM.__new__(LocalVM)

    mgr._vm = vm
    mgr._instance = "test"
    mgr._lock = asyncio.Lock()
    return mgr


# ===========================================================================
# LocalVM (Windows)
# ===========================================================================


class TestStart:
    """Tests for start()."""

    async def test_start_calls_vm_start(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        await mgr.start()

        vm.start.assert_awaited_once()

    async def test_start_is_idempotent_when_running(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.start()
        await mgr.start()

        vm.start.assert_not_awaited()

    async def test_start_does_not_apply_mounts(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        await mgr.start()

        vm.apply_mounts.assert_not_awaited()


class TestStop:
    """Tests for stop()."""

    async def test_stop_calls_vm_stop(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.stop()

        vm.stop.assert_awaited_once()

    async def test_stop_noop_when_not_running(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        await mgr.stop()

        vm.stop.assert_not_awaited()


class TestMount:
    """Tests for mount()."""

    async def test_mount_single_system_scope(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()

        await mgr.mount(Mount(source=str(d), target="code"))

        vm.apply_mounts.assert_awaited_once()
        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 1
        assert applied[0].guest_path == "/mnt/code"
        assert applied[0].host_path == str(d)

    async def test_mount_session_scope(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "project"
        d.mkdir()

        await mgr.mount(Mount(source=str(d), target="project"), session="alice")

        vm.apply_mounts.assert_awaited_once()
        applied = vm.apply_mounts.call_args[0][0]
        assert applied[0].guest_path == "/sessions/alice/mnt/project"

    async def test_mount_validates_source_exists(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        with pytest.raises(ValueError, match="does not exist"):
            await mgr.mount(Mount(source=str(tmp_path / "nope"), target="x"))

    async def test_mount_detects_conflict(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()

        await mgr.mount(Mount(source=str(d1), target="same"))

        vm.read_mounts = lambda: [ResolvedMount(host_path=str(d1), guest_path="/mnt/same", writable=False)]

        with pytest.raises(VMMountConflictError, match="conflict"):
            await mgr.mount(Mount(source=str(d2), target="same"))

    async def test_mount_idempotent(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()

        vm.read_mounts = lambda: [ResolvedMount(host_path=str(d), guest_path="/mnt/code", writable=False)]

        await mgr.mount(Mount(source=str(d), target="code"))

        vm.apply_mounts.assert_not_awaited()

    async def test_mount_empty_list_is_noop(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.mount([])

        vm.apply_mounts.assert_not_awaited()

    async def test_mount_batch_conflict(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()

        with pytest.raises(VMMountConflictError, match="conflict"):
            await mgr.mount(
                [
                    Mount(source=str(d1), target="same"),
                    Mount(source=str(d2), target="same"),
                ]
            )


class TestUnmount:
    """Tests for unmount()."""

    async def test_unmount_system(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/h", guest_path="/mnt/x", writable=False),
        ]

        await mgr.unmount("x")

        vm.apply_mounts.assert_awaited_once()
        assert len(vm.apply_mounts.call_args[0][0]) == 0

    async def test_unmount_nonexistent_is_noop(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.unmount("nope")

        vm.apply_mounts.assert_not_awaited()

    async def test_unmount_defer(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/h", guest_path="/mnt/x", writable=False),
        ]

        await mgr.unmount("x", defer=True)

        vm.apply_mounts.assert_not_awaited()
        vm.write_mounts.assert_called_once()


class TestListMounts:
    """Tests for list_mounts()."""

    def test_list_all_mounts(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/a", guest_path="/mnt/a", writable=False),
            ResolvedMount(host_path="/b", guest_path="/sessions/alice/mnt/b", writable=True),
        ]

        result = mgr.list_mounts()

        assert len(result) == 2

    def test_list_filters_by_session(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/a", guest_path="/mnt/a", writable=False),
            ResolvedMount(host_path="/b", guest_path="/sessions/alice/mnt/b", writable=True),
        ]

        result = mgr.list_mounts(session="alice")

        assert len(result) == 1
        assert result[0].guest_path == "/sessions/alice/mnt/b"


class TestSession:
    """Tests for computer()."""

    async def test_creates_new_session(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])

        computer = await mgr.computer()

        assert isinstance(computer, _VMSessionComputer)
        assert computer.session_name is not None

    async def test_resume_existing(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_ok(stdout="1001"))

        computer = await mgr.computer(resume="my-session")

        assert computer.session_name == "my-session"

    async def test_resume_nonexistent_raises(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_fail(stderr="no such user"))

        with pytest.raises(VMError, match="does not exist"):
            await mgr.computer(resume="ghost")

    async def test_rejects_resume_with_mounts(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        with pytest.raises(ValueError, match="Cannot specify 'mounts'"):
            await mgr.computer(resume="x", mounts=[Mount(source="/tmp", target="t")])

    async def test_auto_starts_if_needed(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])

        await mgr.computer()

        vm.start.assert_awaited_once()


class TestDestroySession:
    """Tests for destroy()."""

    async def test_destroy_calls_userdel(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.destroy("test-user")

        last_call = vm.shell.call_args_list[-1]
        assert "userdel -r test-user" in last_call.args[0]

    async def test_destroy_removes_session_mounts(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/x", guest_path="/sessions/test-user/mnt/x", writable=False),
            ResolvedMount(host_path="/sys", guest_path="/mnt/sys", writable=False),
        ]

        await mgr.destroy("test-user")

        vm.apply_mounts.assert_awaited_once()
        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 1
        assert applied[0].guest_path == "/mnt/sys"


class TestListSessions:
    """Tests for list_sessions()."""

    async def test_list_requires_running(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        with pytest.raises(VMError, match="not running"):
            await mgr.list_sessions()

    async def test_list_returns_session_names(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_ok(stdout="alpha bravo charlie"))

        result = await mgr.list_sessions()

        assert result == ["alpha", "bravo", "charlie"]


class TestApply:
    """Tests for apply()."""

    async def test_apply_restarts_running_distro(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.apply()

        vm.stop.assert_awaited_once()
        vm.start.assert_awaited_once()

    async def test_apply_starts_stopped_distro(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        await mgr.apply()

        vm.stop.assert_not_awaited()
        vm.start.assert_awaited_once()

    async def test_apply_raises_if_missing(self) -> None:
        vm = _mock_vm()
        vm.status = AsyncMock(return_value=None)
        mgr = _make_manager(vm)

        with pytest.raises(VMError, match="does not exist"):
            await mgr.apply()


class TestMountDefer:
    """Tests for mount(defer=True)."""

    async def test_mount_defer_writes_config_without_restart(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()

        await mgr.mount(Mount(source=str(d), target="code"), defer=True)

        vm.apply_mounts.assert_not_awaited()
        vm.write_mounts.assert_called_once()
        written = vm.write_mounts.call_args[0][0]
        assert len(written) == 1
        assert written[0].guest_path == "/mnt/code"


class TestMountResolution:
    """Tests for _resolve_mount() and _target_to_guest()."""

    def test_relative_target_system(self) -> None:
        m = Mount(source="/host/skills", target=".skills/coding")
        resolved = LocalVM._resolve_mount(m, scope="system")
        assert resolved.guest_path == "/mnt/.skills/coding"

    def test_relative_target_session(self) -> None:
        m = Mount(source="/host/project", target="project")
        resolved = LocalVM._resolve_mount(m, scope="session", session_name="alice")
        assert resolved.guest_path == "/sessions/alice/mnt/project"

    def test_absolute_target(self) -> None:
        m = Mount(source="/host/tools", target="/opt/tools")
        resolved = LocalVM._resolve_mount(m, scope="system")
        assert resolved.guest_path == "/opt/tools"

    def test_target_to_guest_system(self) -> None:
        assert LocalVM._target_to_guest("code", "system") == "/mnt/code"

    def test_target_to_guest_session(self) -> None:
        assert LocalVM._target_to_guest("proj", "session", "alice") == "/sessions/alice/mnt/proj"


class TestCreateUser:
    """Tests for _create_user."""

    async def test_creates_session_dirs(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(side_effect=[_ok(), _ok()])

        await mgr._create_user("test-user")

        setup_call = vm.shell.call_args_list[1].args[0]
        home = "/sessions/test-user"
        for d in SESSION_DIRS:
            assert f"{home}/{d}" in setup_call
        assert "mkdir -p" in setup_call

    async def test_useradd_failure_raises(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_fail(stderr="already exists"))

        with pytest.raises(VMError, match="Failed to create session user"):
            await mgr._create_user("test-user")


class TestNameGeneration:
    """Tests for _generate_unique_name."""

    async def test_first_name_is_unique(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_fail())

        name = await mgr._generate_unique_name()

        assert isinstance(name, str)
        assert len(name) > 0

    async def test_raises_after_max_attempts(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_ok())

        with pytest.raises(VMError, match="Failed to generate"):
            await mgr._generate_unique_name(max_attempts=3)


class TestSessionAtomicity:
    """Tests for atomic session creation with cleanup."""

    async def test_mount_failure_cleans_up_user(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "nope"

        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])

        with pytest.raises(ValueError, match="does not exist"):
            await mgr.computer(mounts=[Mount(source=str(d), target="proj")])

        last_call = vm.shell.call_args_list[-1].args[0]
        assert "userdel -r" in last_call
