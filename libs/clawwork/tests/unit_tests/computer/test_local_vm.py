# ruff: noqa: ANN401, PLR2004, S108
"""Tests for LocalVM.

All tests mock the LimaVM backend — no Lima or limactl required.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest

from clawwork.computer.base import SESSION_DIRS, Mount
from clawwork.computer.local._types import ResolvedMount
from clawwork.computer.local.vm import LocalVM, _VMSessionComputer
from clawwork.exceptions import VMError, VMMountConflictError
from clawwork.types import CLIResult

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
    """Create a LocalVM with a mocked VM backend."""
    with patch("clawwork.computer.local.vm.sys") as mock_sys:
        mock_sys.platform = "darwin"
        with patch("clawwork.computer.local.vm.LocalVM.__init__", return_value=None):
            mgr = LocalVM.__new__(LocalVM)

    mgr._vm = vm
    mgr._instance = "test"
    mgr._lock = asyncio.Lock()
    return mgr


# ===========================================================================
# LocalVM
# ===========================================================================


class TestStart:
    """Tests for start()."""

    async def test_start_calls_vm_start(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        await mgr.start()

        vm.start.assert_awaited_once()

    async def test_start_is_idempotent_when_running(self) -> None:
        vm = _mock_vm()  # status="Running"
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
        vm = _mock_vm()  # status="Running"
        mgr = _make_manager(vm)

        await mgr.stop()

        vm.stop.assert_awaited_once()

    async def test_stop_noop_when_not_running(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        await mgr.stop()

        vm.stop.assert_not_awaited()


class TestMount:
    """Tests for mount() — reads lima.yaml, merges, applies."""

    async def test_mount_single_system_scope(self, tmp_path: Any) -> None:
        """System mount merges with lima.yaml and applies."""
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

    async def test_mount_batch_system_scope(self, tmp_path: Any) -> None:
        """Batch mount applies all mounts in one call."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()

        await mgr.mount([Mount(source=str(d1), target="a"), Mount(source=str(d2), target="b")])

        vm.apply_mounts.assert_awaited_once()
        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 2

    async def test_mount_session_scope(self, tmp_path: Any) -> None:
        """Session mount resolves to /sessions/<name>/mnt/<target>."""
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

    async def test_mount_validates_source_is_dir(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        f = tmp_path / "file.txt"
        f.write_text("x")

        with pytest.raises(ValueError, match="not a directory"):
            await mgr.mount(Mount(source=str(f), target="x"))

    async def test_mount_detects_conflict_within_scope(self, tmp_path: Any) -> None:
        """Second mount to same guest path with different source collides."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()

        await mgr.mount(Mount(source=str(d1), target="same"))

        # lima.yaml now has mount at /mnt/same
        vm.read_mounts = lambda: [ResolvedMount(host_path=str(d1), guest_path="/mnt/same", writable=False)]

        with pytest.raises(VMMountConflictError, match="conflict"):
            await mgr.mount(Mount(source=str(d2), target="same"))

    async def test_mount_detects_cross_scope_conflict(self, tmp_path: Any) -> None:
        """System and session mount to same absolute guest path collide."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()

        await mgr.mount(Mount(source=str(d1), target="/opt/tools"))

        # lima.yaml now has /opt/tools
        vm.read_mounts = lambda: [ResolvedMount(host_path=str(d1), guest_path="/opt/tools", writable=False)]

        with pytest.raises(VMMountConflictError, match="conflict"):
            await mgr.mount(Mount(source=str(d2), target="/opt/tools"), session="alice")

    async def test_mount_detects_conflict_with_lima_yaml(self, tmp_path: Any) -> None:
        """Collision is detected against mounts already in lima.yaml."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()

        # lima.yaml already has a mount at /mnt/code from a previous process
        vm.read_mounts = lambda: [ResolvedMount(host_path="/other", guest_path="/mnt/code", writable=False)]

        with pytest.raises(VMMountConflictError, match="conflict"):
            await mgr.mount(Mount(source=str(d), target="code"))

    async def test_mount_to_nonexistent_session_raises(self, tmp_path: Any) -> None:
        """Mounting to unknown session checks VM and raises."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()
        vm.shell = AsyncMock(return_value=_fail(stderr="no such user"))

        with pytest.raises(VMError, match="does not exist"):
            await mgr.mount(Mount(source=str(d), target="code"), session="ghost")

    async def test_mount_session_validates_user_exists(self, tmp_path: Any) -> None:
        """Session mount always validates user exists on VM via id -u."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()

        await mgr.mount(Mount(source=str(d), target="code"), session="alice")

        # id -u was called to validate user
        vm.shell.assert_awaited_once()
        assert "id -u alice" in vm.shell.call_args[0][0]

    async def test_mount_incremental(self, tmp_path: Any) -> None:
        """Multiple mounts accumulate in lima.yaml, not replace."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()

        await mgr.mount(Mount(source=str(d1), target="a"))

        # lima.yaml now has mount "a"
        vm.read_mounts = lambda: [ResolvedMount(host_path=str(d1), guest_path="/mnt/a", writable=False)]

        await mgr.mount(Mount(source=str(d2), target="b"))

        # Second apply merges both mounts
        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 2
        guests = {m.guest_path for m in applied}
        assert guests == {"/mnt/a", "/mnt/b"}

    async def test_mount_idempotent_when_already_exists(self, tmp_path: Any) -> None:
        """Mounting something already in lima.yaml is a no-op."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()

        # lima.yaml already has this exact mount
        vm.read_mounts = lambda: [ResolvedMount(host_path=str(d), guest_path="/mnt/code", writable=False)]

        await mgr.mount(Mount(source=str(d), target="code"))

        vm.apply_mounts.assert_not_awaited()

    async def test_mount_empty_list_is_noop(self) -> None:
        """Passing an empty list does nothing."""
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.mount([])

        vm.apply_mounts.assert_not_awaited()

    async def test_mount_batch_detects_within_batch_conflict(self, tmp_path: Any) -> None:
        """Two mounts in the same batch targeting the same guest path collide."""
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

    async def test_mount_preserves_existing_lima_yaml_mounts(self, tmp_path: Any) -> None:
        """New mount is appended to existing lima.yaml mounts, not replaced."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "new"
        d.mkdir()

        # lima.yaml has existing mounts from a previous process
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/old/skills", guest_path="/mnt/skills/coding", writable=False),
            ResolvedMount(host_path="/old/data", guest_path="/mnt/data", writable=False),
        ]

        await mgr.mount(Mount(source=str(d), target="new"))

        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 3
        guests = {m.guest_path for m in applied}
        assert guests == {"/mnt/skills/coding", "/mnt/data", "/mnt/new"}


class TestUnmount:
    """Tests for unmount() — reads lima.yaml, removes, applies."""

    async def test_unmount_system(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/h", guest_path="/mnt/x", writable=False),
        ]

        await mgr.unmount("x")

        vm.apply_mounts.assert_awaited_once()
        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 0

    async def test_unmount_session(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/h", guest_path="/sessions/alice/mnt/proj", writable=False),
        ]

        await mgr.unmount("proj", session="alice")

        vm.apply_mounts.assert_awaited_once()
        assert len(vm.apply_mounts.call_args[0][0]) == 0

    async def test_unmount_nonexistent_is_noop(self) -> None:
        """Unmounting a target not in lima.yaml is idempotent."""
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.unmount("nope")

        vm.apply_mounts.assert_not_awaited()

    async def test_unmount_from_empty_session_is_noop(self) -> None:
        """Unmounting from a session with no mounts is idempotent."""
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.unmount("x", session="alice")

        vm.apply_mounts.assert_not_awaited()

    async def test_unmount_batch(self) -> None:
        """Batch unmount removes multiple targets and applies once."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/a", guest_path="/mnt/a", writable=False),
            ResolvedMount(host_path="/b", guest_path="/mnt/b", writable=False),
            ResolvedMount(host_path="/c", guest_path="/mnt/c", writable=False),
        ]

        await mgr.unmount(["a", "c"])

        vm.apply_mounts.assert_awaited_once()
        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 1
        assert applied[0].guest_path == "/mnt/b"

    async def test_unmount_batch_partial_missing_is_ok(self) -> None:
        """Batch where some targets don't exist still removes the ones that do."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/a", guest_path="/mnt/a", writable=False),
        ]

        await mgr.unmount(["a", "missing"])

        vm.apply_mounts.assert_awaited_once()
        assert len(vm.apply_mounts.call_args[0][0]) == 0

    async def test_unmount_defer_writes_yaml_without_restart(self) -> None:
        """defer=True writes to lima.yaml but does not restart the VM."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/h", guest_path="/mnt/x", writable=False),
        ]

        await mgr.unmount("x", defer=True)

        vm.apply_mounts.assert_not_awaited()
        vm.write_mounts.assert_called_once()
        assert vm.write_mounts.call_args[0][0] == []

    async def test_unmount_defer_then_mount_no_conflict(self, tmp_path: Any) -> None:
        """Deferred unmount updates lima.yaml so remount at same path works."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/old", guest_path="/sessions/alice/mnt/proj", writable=False),
        ]

        await mgr.unmount("proj", session="alice", defer=True)
        vm.write_mounts.assert_called_once()

        # Simulate lima.yaml now empty (write_mounts was called)
        vm.read_mounts = list

        d = tmp_path / "new_proj"
        d.mkdir()

        # Mount new dir at same target — no conflict since yaml was updated
        await mgr.mount(Mount(source=str(d), target="proj"), session="alice")
        vm.apply_mounts.assert_awaited_once()

    async def test_unmount_empty_list_is_noop(self) -> None:
        """Passing an empty list does nothing."""
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.unmount([])

        vm.apply_mounts.assert_not_awaited()

    async def test_unmount_preserves_other_mounts(self) -> None:
        """Unmounting one target preserves all other mounts."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/skills", guest_path="/mnt/skills/coding", writable=False),
            ResolvedMount(host_path="/data", guest_path="/mnt/data", writable=False),
            ResolvedMount(host_path="/proj", guest_path="/sessions/alice/mnt/proj", writable=True),
        ]

        await mgr.unmount("proj", session="alice")

        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 2
        guests = {m.guest_path for m in applied}
        assert guests == {"/mnt/skills/coding", "/mnt/data"}


class TestListMounts:
    """Tests for list_mounts() — reads from lima.yaml (source of truth)."""

    def test_list_all_mounts(self) -> None:
        """Without session filter, returns all mounts from lima.yaml."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/a", guest_path="/mnt/a", writable=False),
            ResolvedMount(host_path="/b", guest_path="/sessions/alice/mnt/b", writable=True),
        ]

        result = mgr.list_mounts()

        assert len(result) == 2

    def test_list_filters_by_session(self) -> None:
        """With session filter, returns only that session's mounts."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/a", guest_path="/mnt/a", writable=False),
            ResolvedMount(host_path="/b", guest_path="/sessions/alice/mnt/b", writable=True),
            ResolvedMount(host_path="/c", guest_path="/sessions/bob/mnt/c", writable=False),
        ]

        result = mgr.list_mounts(session="alice")

        assert len(result) == 1
        assert result[0].guest_path == "/sessions/alice/mnt/b"

    def test_list_unknown_session_returns_empty(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/a", guest_path="/mnt/a", writable=False),
        ]

        assert mgr.list_mounts(session="ghost") == []

    def test_list_survives_manager_restart(self) -> None:
        """Mounts persist in lima.yaml even with fresh in-memory state."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        # Fresh manager — no in-memory state
        # But lima.yaml has mounts
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/h", guest_path="/mnt/code", writable=False),
        ]

        result = mgr.list_mounts()

        assert len(result) == 1
        assert result[0].guest_path == "/mnt/code"


class TestSession:
    """Tests for session()."""

    async def test_creates_new_session(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        # id -u fails (unique), useradd succeeds, mkdir succeeds
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])

        computer = await mgr.computer()

        assert isinstance(computer, _VMSessionComputer)
        assert computer.session_name is not None

    async def test_session_with_mounts(self, tmp_path: Any) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "project"
        d.mkdir()
        # id -u fails (unique), useradd succeeds, mkdir succeeds, id -u succeeds (mount validation)
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])

        computer = await mgr.computer(mounts=[Mount(source=str(d), target="project")])

        assert computer.session_name is not None
        vm.apply_mounts.assert_awaited_once()

    async def test_resume_existing(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        # id -u succeeds (user exists)
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
        # id -u fails (unique), useradd succeeds, mkdir succeeds
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok()])

        await mgr.computer()

        vm.start.assert_awaited_once()

    async def test_session_conflict_with_lima_yaml(self, tmp_path: Any) -> None:
        """Session mounts check lima.yaml for conflicts."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "proj"
        d.mkdir()
        # id -u fails (unique), useradd succeeds, mkdir succeeds,
        # id -u succeeds (mount validation), userdel cleanup after conflict
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok(), _ok()])

        # lima.yaml has a mount at /opt/shared
        vm.read_mounts = lambda: [
            ResolvedMount(host_path="/other", guest_path="/opt/shared", writable=False),
        ]

        with pytest.raises(VMMountConflictError, match="conflict"):
            await mgr.computer(mounts=[Mount(source=str(d), target="/opt/shared")])


class TestDestroySession:
    """Tests for destroy_session()."""

    async def test_destroy_calls_userdel(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.destroy("test-user")

        last_call = vm.shell.call_args_list[-1]
        assert "userdel -r test-user" in last_call.args[0]

    async def test_destroy_removes_session_mounts_from_yaml(self) -> None:
        """Session mounts are removed from lima.yaml on destroy."""
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

    async def test_destroy_noop_when_no_session_mounts(self) -> None:
        """No apply_mounts call if session had no mounts."""
        vm = _mock_vm()
        mgr = _make_manager(vm)

        await mgr.destroy("test-user")

        vm.apply_mounts.assert_not_awaited()


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

    async def test_list_returns_empty_on_failure(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_fail())

        assert await mgr.list_sessions() == []


class TestMountResolution:
    """Tests for _resolve_mount() and _target_to_guest()."""

    def test_relative_target_system(self) -> None:
        from clawwork.computer.local.vm import LocalVM

        m = Mount(source="/host/skills", target=".skills/coding")
        resolved = LocalVM._resolve_mount(m, scope="system")
        assert resolved.guest_path == "/mnt/.skills/coding"

    def test_relative_target_session(self) -> None:
        from clawwork.computer.local.vm import LocalVM

        m = Mount(source="/host/project", target="project")
        resolved = LocalVM._resolve_mount(m, scope="session", session_name="alice")
        assert resolved.guest_path == "/sessions/alice/mnt/project"

    def test_absolute_target(self) -> None:
        from clawwork.computer.local.vm import LocalVM

        m = Mount(source="/host/tools", target="/opt/tools")
        resolved = LocalVM._resolve_mount(m, scope="system")
        assert resolved.guest_path == "/opt/tools"

    def test_writable_preserved(self) -> None:
        from clawwork.computer.local.vm import LocalVM

        m = Mount(source="/host/x", target="x", writable=True)
        resolved = LocalVM._resolve_mount(m, scope="system")
        assert resolved.writable is True

    def test_target_to_guest_system(self) -> None:
        from clawwork.computer.local.vm import LocalVM

        assert LocalVM._target_to_guest("code", "system") == "/mnt/code"

    def test_target_to_guest_session(self) -> None:
        from clawwork.computer.local.vm import LocalVM

        assert LocalVM._target_to_guest("proj", "session", "alice") == "/sessions/alice/mnt/proj"

    def test_target_to_guest_absolute(self) -> None:
        from clawwork.computer.local.vm import LocalVM

        assert LocalVM._target_to_guest("/opt/tools", "system") == "/opt/tools"


class TestCreateUser:
    """Tests for _create_user."""

    async def test_creates_session_dirs(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(side_effect=[_ok(), _ok()])

        await mgr._create_user("test-user")

        setup_call = vm.shell.call_args_list[1].args[0]
        home = "/sessions/test-user"
        # All dirs are created with mkdir (shell-quoted)
        for d in SESSION_DIRS:
            assert f"{home}/{d}" in setup_call
        assert "mkdir -p" in setup_call

    async def test_useradd_failure_raises(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_fail(stderr="already exists"))

        with pytest.raises(VMError, match="Failed to create session user"):
            await mgr._create_user("test-user")

    async def test_mkdir_failure_raises(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(side_effect=[_ok(), _fail(stderr="permission denied")])

        with pytest.raises(VMError, match="Failed to create session directories"):
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

    async def test_retries_on_conflict(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(side_effect=[_ok(), _ok(), _fail()])

        name = await mgr._generate_unique_name()

        assert isinstance(name, str)
        assert vm.shell.await_count == 3

    async def test_raises_after_max_attempts(self) -> None:
        vm = _mock_vm()
        mgr = _make_manager(vm)
        vm.shell = AsyncMock(return_value=_ok())

        with pytest.raises(VMError, match="Failed to generate"):
            await mgr._generate_unique_name(max_attempts=3)

        assert vm.shell.await_count == 3


class TestMountDefer:
    """Tests for mount(defer=True)."""

    async def test_mount_defer_writes_yaml_without_restart(self, tmp_path: Any) -> None:
        """defer=True writes to lima.yaml but does not restart the VM."""
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

    async def test_mount_defer_then_apply(self, tmp_path: Any) -> None:
        """Deferred mount followed by apply() restarts the VM."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "code"
        d.mkdir()

        await mgr.mount(Mount(source=str(d), target="code"), defer=True)
        await mgr.apply()

        vm.apply_mounts.assert_not_awaited()
        vm.stop.assert_awaited_once()
        vm.start.assert_awaited_once()

    async def test_mount_defer_and_immediate_mix(self, tmp_path: Any) -> None:
        """Deferred mount + immediate mount applies only the immediate one."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d1 = tmp_path / "a"
        d2 = tmp_path / "b"
        d1.mkdir()
        d2.mkdir()

        await mgr.mount(Mount(source=str(d1), target="a"), defer=True)

        # Simulate lima.yaml updated by deferred mount
        vm.read_mounts = lambda: [
            ResolvedMount(host_path=str(d1), guest_path="/mnt/a", writable=False),
        ]

        await mgr.mount(Mount(source=str(d2), target="b"))

        vm.apply_mounts.assert_awaited_once()
        applied = vm.apply_mounts.call_args[0][0]
        assert len(applied) == 2


class TestApply:
    """Tests for apply()."""

    async def test_apply_restarts_running_vm(self) -> None:
        vm = _mock_vm()  # status="Running"
        mgr = _make_manager(vm)

        await mgr.apply()

        vm.stop.assert_awaited_once()
        vm.start.assert_awaited_once()

    async def test_apply_starts_stopped_vm(self) -> None:
        vm = _mock_vm(status="Stopped")
        mgr = _make_manager(vm)

        await mgr.apply()

        vm.stop.assert_not_awaited()
        vm.start.assert_awaited_once()

    async def test_apply_raises_if_instance_missing(self) -> None:
        vm = _mock_vm()
        vm.status = AsyncMock(return_value=None)
        mgr = _make_manager(vm)

        with pytest.raises(VMError, match="does not exist"):
            await mgr.apply()


class TestSessionAtomicity:
    """Tests for atomic session creation with cleanup."""

    async def test_mount_failure_cleans_up_user(self, tmp_path: Any) -> None:
        """If mount fails after user creation, the user is deleted."""
        vm = _mock_vm()
        mgr = _make_manager(vm)
        d = tmp_path / "nope"  # Does not exist — will fail validation

        # id -u fails (unique name), useradd succeeds, mkdir succeeds
        vm.shell = AsyncMock(side_effect=[_fail(), _ok(), _ok(), _ok()])

        with pytest.raises(ValueError, match="does not exist"):
            await mgr.computer(mounts=[Mount(source=str(d), target="proj")])

        # Last shell call should be userdel cleanup
        last_call = vm.shell.call_args_list[-1].args[0]
        assert "userdel -r" in last_call
