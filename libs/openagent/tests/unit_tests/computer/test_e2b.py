"""Tests for RemoteE2BComputer."""

from __future__ import annotations

import builtins
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openagent.computer.remote.e2b import (
    _E2B_MAX_LIFETIME_S,
    SANDBOX_DEFAULT_LIFETIME_S,
    RemoteE2BComputer,
)
from openagent.exceptions import CLIError, ConfigurationError, MissingDependencyError

if TYPE_CHECKING:
    from collections.abc import Generator
    from types import ModuleType

# Test constants
_CUSTOM_LIFETIME = 300
_CUSTOM_TIMEOUT_MS = 5000.0
_ONE_HOUR_MS = 3600000.0


@pytest.fixture
def mock_env() -> Generator[None, None, None]:
    """Set E2B_API_KEY for tests."""
    with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
        yield


@pytest.fixture
def mock_sandbox() -> MagicMock:
    """Create a mock AsyncSandbox."""
    sandbox = MagicMock()
    sandbox.sandbox_id = "sandbox-123"

    # Mock commands.run
    run_result = MagicMock()
    run_result.stdout = "output"
    run_result.stderr = ""
    run_result.exit_code = 0
    sandbox.commands = MagicMock()
    sandbox.commands.run = AsyncMock(return_value=run_result)

    # Mock lifecycle methods
    sandbox.beta_pause = AsyncMock()
    sandbox.kill = AsyncMock()
    sandbox.set_timeout = AsyncMock()

    # Mock get_info
    info = MagicMock()
    info.started_at = datetime.now(UTC) - timedelta(seconds=60)
    info.end_at = datetime.now(UTC) + timedelta(seconds=300)
    sandbox.get_info = AsyncMock(return_value=info)

    return sandbox


@pytest.fixture
def mock_e2b_module() -> MagicMock:
    """Create a mock e2b module with AsyncSandbox and CommandExitException."""
    mock_module = MagicMock()

    # Create mock AsyncSandbox class
    mock_sandbox_class = MagicMock()
    mock_module.AsyncSandbox = mock_sandbox_class

    # Create mock CommandExitException
    class _MockCommandExitError(Exception):
        def __init__(
            self,
            stdout: str = "",
            stderr: str = "",
            exit_code: int = 1,
        ) -> None:
            self.stdout = stdout
            self.stderr = stderr
            self.exit_code = exit_code
            super().__init__()

    mock_module.CommandExitException = _MockCommandExitError

    return mock_module


class TestInit:
    """Tests for __init__."""

    def test_missing_api_key_raises_configuration_error(self) -> None:
        """Test ConfigurationError when E2B_API_KEY is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure E2B_API_KEY is not in environment
            os.environ.pop("E2B_API_KEY", None)
            with pytest.raises(ConfigurationError, match="E2B_API_KEY"):
                RemoteE2BComputer()

    @pytest.mark.usefixtures("mock_env")
    def test_default_initialization(self) -> None:
        """Test default values are set correctly."""
        computer = RemoteE2BComputer()
        assert computer._template is None
        assert computer._lifetime == SANDBOX_DEFAULT_LIFETIME_S
        assert computer._sandbox_id is None
        assert not computer._is_paused

    @pytest.mark.usefixtures("mock_env")
    def test_custom_template_and_lifetime(self) -> None:
        """Test custom template and lifetime."""
        computer = RemoteE2BComputer(template="custom-template", lifetime=_CUSTOM_LIFETIME)
        assert computer._template == "custom-template"
        assert computer._lifetime == _CUSTOM_LIFETIME

    @pytest.mark.usefixtures("mock_env")
    def test_sandbox_id_sets_paused_state(self) -> None:
        """Test sandbox_id sets is_paused to True for reconnection."""
        computer = RemoteE2BComputer(sandbox_id="existing-sandbox")
        assert computer._sandbox_id == "existing-sandbox"
        assert computer._is_paused is True


class TestProperties:
    """Tests for properties."""

    @pytest.mark.usefixtures("mock_env")
    def test_sandbox_id_returns_sandbox_id_when_running(self, mock_sandbox: MagicMock) -> None:
        """Test sandbox_id returns sandbox.sandbox_id when sandbox exists."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        assert computer.sandbox_id == "sandbox-123"

    @pytest.mark.usefixtures("mock_env")
    def test_sandbox_id_returns_cached_when_no_sandbox(self) -> None:
        """Test sandbox_id returns cached _sandbox_id when sandbox is None."""
        computer = RemoteE2BComputer()
        computer._sandbox_id = "cached-id"
        assert computer.sandbox_id == "cached-id"

    @pytest.mark.usefixtures("mock_env")
    def test_is_running_true_when_active(self, mock_sandbox: MagicMock) -> None:
        """Test is_running returns True when sandbox exists and not paused."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False
        assert computer.is_running is True

    @pytest.mark.usefixtures("mock_env")
    def test_is_running_false_when_no_sandbox(self) -> None:
        """Test is_running returns False when sandbox is None."""
        computer = RemoteE2BComputer()
        assert computer.is_running is False

    @pytest.mark.usefixtures("mock_env")
    def test_is_running_false_when_paused(self, mock_sandbox: MagicMock) -> None:
        """Test is_running returns False when paused."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = True
        assert computer.is_running is False


class TestStart:
    """Tests for start()."""

    @pytest.mark.usefixtures("mock_env")
    async def test_start_idempotent_when_running(self, mock_sandbox: MagicMock) -> None:
        """Test start() is no-op when already running."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        await computer.start()
        # Should not try to create or connect
        assert computer._sandbox is mock_sandbox

    @pytest.mark.usefixtures("mock_env")
    async def test_start_raises_missing_dependency(self) -> None:
        """Test MissingDependencyError when e2b not installed.

        This test verifies the error path when the e2b package is not installed.
        Since e2b is likely installed in the test environment, we mock the import
        to simulate the missing dependency scenario.
        """
        computer = RemoteE2BComputer()

        # Save original e2b module reference and remove from sys.modules
        original_e2b: ModuleType | None = sys.modules.pop("e2b", None)
        # Also remove any e2b submodules
        e2b_submodules: dict[str, ModuleType] = {k: v for k, v in sys.modules.items() if k.startswith("e2b.")}
        for key in e2b_submodules:
            sys.modules.pop(key, None)

        try:
            original_import = builtins.__import__

            def mock_import(
                name: str,
                globs: dict[str, Any] | None = None,
                locs: dict[str, Any] | None = None,
                fromlist: tuple[str, ...] = (),
                level: int = 0,
            ) -> ModuleType:
                if name == "e2b" or name.startswith("e2b."):
                    msg = "No module named 'e2b'"
                    raise ImportError(msg)
                return original_import(name, globs, locs, fromlist, level)

            builtins.__import__ = mock_import  # type: ignore[assignment]
            try:
                with pytest.raises(MissingDependencyError, match="E2B package"):
                    await computer.start()
            finally:
                builtins.__import__ = original_import
        finally:
            # Restore e2b modules
            if original_e2b is not None:
                sys.modules["e2b"] = original_e2b
            sys.modules.update(e2b_submodules)

    @pytest.mark.usefixtures("mock_env")
    async def test_start_reconnects_existing_sandbox(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test start() reconnects to existing sandbox_id."""
        computer = RemoteE2BComputer(sandbox_id="existing-sandbox")

        mock_e2b_module.AsyncSandbox.connect = AsyncMock(return_value=mock_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            await computer.start()

            mock_e2b_module.AsyncSandbox.connect.assert_called_once_with("existing-sandbox", timeout=SANDBOX_DEFAULT_LIFETIME_S)
            assert computer._sandbox is mock_sandbox
            assert not computer._is_paused

    @pytest.mark.usefixtures("mock_env")
    async def test_start_creates_new_on_reconnect_failure(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test start() creates new sandbox when reconnection fails."""
        computer = RemoteE2BComputer(sandbox_id="expired-sandbox")

        mock_e2b_module.AsyncSandbox.connect = AsyncMock(side_effect=Exception("Sandbox not found"))
        mock_e2b_module.AsyncSandbox.create = AsyncMock(return_value=mock_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            await computer.start()

            mock_e2b_module.AsyncSandbox.connect.assert_called_once()
            mock_e2b_module.AsyncSandbox.create.assert_called_once_with(None, timeout=SANDBOX_DEFAULT_LIFETIME_S)
            assert computer._sandbox is mock_sandbox
            assert computer._sandbox_id == "sandbox-123"

    @pytest.mark.usefixtures("mock_env")
    async def test_start_creates_new_sandbox(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test start() creates new sandbox when no sandbox_id."""
        computer = RemoteE2BComputer(template="my-template", lifetime=500)

        mock_e2b_module.AsyncSandbox.create = AsyncMock(return_value=mock_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            await computer.start()

            mock_e2b_module.AsyncSandbox.create.assert_called_once_with("my-template", timeout=500)
            assert computer._sandbox is mock_sandbox
            assert computer._sandbox_id == "sandbox-123"
            assert not computer._is_paused

    @pytest.mark.usefixtures("mock_env")
    async def test_start_raises_cli_error_on_create_failure(self, mock_e2b_module: MagicMock) -> None:
        """Test start() raises CLIError when sandbox creation fails."""
        computer = RemoteE2BComputer()

        mock_e2b_module.AsyncSandbox.create = AsyncMock(side_effect=Exception("API error"))

        with (
            patch.dict(sys.modules, {"e2b": mock_e2b_module}),
            pytest.raises(CLIError, match="Failed to create E2B sandbox"),
        ):
            await computer.start()


class TestPause:
    """Tests for _pause()."""

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_sets_is_paused(self, mock_sandbox: MagicMock) -> None:
        """Test _pause() pauses sandbox and sets flag."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        await computer._pause()

        mock_sandbox.beta_pause.assert_called_once()
        assert computer._is_paused is True
        assert computer._sandbox_id == "sandbox-123"

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_noop_when_already_paused(self, mock_sandbox: MagicMock) -> None:
        """Test _pause() is no-op when already paused."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = True

        await computer._pause()

        mock_sandbox.beta_pause.assert_not_called()

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_noop_when_no_sandbox(self) -> None:
        """Test _pause() is no-op when no sandbox."""
        computer = RemoteE2BComputer()
        await computer._pause()  # Should not raise

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_raises_cli_error_on_failure(self, mock_sandbox: MagicMock) -> None:
        """Test _pause() raises CLIError on failure."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        mock_sandbox.beta_pause.side_effect = Exception("Pause failed")

        with pytest.raises(CLIError, match="Failed to pause sandbox"):
            await computer._pause()


class TestStop:
    """Tests for stop()."""

    @pytest.mark.usefixtures("mock_env")
    async def test_stop_calls_pause(self, mock_sandbox: MagicMock) -> None:
        """Test stop() calls _pause()."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox

        await computer.stop()

        mock_sandbox.beta_pause.assert_called_once()

    @pytest.mark.usefixtures("mock_env")
    async def test_stop_falls_back_to_kill_on_pause_failure(self, mock_sandbox: MagicMock) -> None:
        """Test stop() falls back to _kill() when pause fails."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        mock_sandbox.beta_pause.side_effect = Exception("Pause failed")

        await computer.stop()

        mock_sandbox.kill.assert_called_once()
        assert computer._sandbox is None
        assert computer._sandbox_id is None

    @pytest.mark.usefixtures("mock_env")
    async def test_stop_idempotent(self) -> None:
        """Test stop() is idempotent when no sandbox."""
        computer = RemoteE2BComputer()
        await computer.stop()  # Should not raise
        await computer.stop()  # Should not raise


class TestKill:
    """Tests for _kill()."""

    @pytest.mark.usefixtures("mock_env")
    async def test_kill_destroys_sandbox(self, mock_sandbox: MagicMock) -> None:
        """Test _kill() destroys sandbox and clears state."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._sandbox_id = "sandbox-123"

        await computer._kill()

        mock_sandbox.kill.assert_called_once()
        assert computer._sandbox is None
        assert computer._sandbox_id is None
        assert not computer._is_paused

    @pytest.mark.usefixtures("mock_env")
    async def test_kill_suppresses_errors(self, mock_sandbox: MagicMock) -> None:
        """Test _kill() suppresses errors during kill."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        mock_sandbox.kill.side_effect = Exception("Kill failed")

        await computer._kill()  # Should not raise

        assert computer._sandbox is None
        assert computer._sandbox_id is None


class TestRun:
    """Tests for run()."""

    @pytest.mark.usefixtures("mock_env")
    async def test_run_auto_starts_if_needed(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() auto-starts sandbox if not running."""
        computer = RemoteE2BComputer()

        mock_e2b_module.AsyncSandbox.create = AsyncMock(return_value=mock_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            result = await computer.run("echo hello")

            mock_e2b_module.AsyncSandbox.create.assert_called_once()
            assert result.stdout == "output"
            assert result.exit_code == 0

    @pytest.mark.usefixtures("mock_env")
    async def test_run_auto_resumes_if_paused(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() resumes paused sandbox."""
        computer = RemoteE2BComputer(sandbox_id="paused-sandbox")

        mock_e2b_module.AsyncSandbox.connect = AsyncMock(return_value=mock_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            result = await computer.run("echo hello")

            mock_e2b_module.AsyncSandbox.connect.assert_called_once()
            assert result.stdout == "output"

    @pytest.mark.usefixtures("mock_env")
    async def test_run_returns_result(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() returns correct CLIResult."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        run_result = MagicMock()
        run_result.stdout = "hello world\n"
        run_result.stderr = "warning\n"
        run_result.exit_code = 0
        mock_sandbox.commands.run.return_value = run_result

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            result = await computer.run("echo hello world")

            assert result.stdout == "hello world"  # Trailing newline stripped
            assert result.stderr == "warning"
            assert result.exit_code == 0
            assert result.metadata is not None
            assert result.metadata.duration_ms >= 0

    @pytest.mark.usefixtures("mock_env")
    async def test_run_handles_command_exit_exception(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() handles CommandExitException for non-zero exit."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        # Create the exception instance
        exc = mock_e2b_module.CommandExitException(
            stdout="partial output",
            stderr="error message",
            exit_code=1,
        )
        mock_sandbox.commands.run.side_effect = exc

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            result = await computer.run("exit 1")

            assert result.stdout == "partial output"
            assert result.stderr == "error message"
            assert result.exit_code == 1

    @pytest.mark.usefixtures("mock_env")
    async def test_run_raises_cli_error_on_timeout(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() raises CLIError on timeout."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        mock_sandbox.commands.run.side_effect = Exception("Command timeout exceeded")

        with (
            patch.dict(sys.modules, {"e2b": mock_e2b_module}),
            pytest.raises(CLIError, match="timed out"),
        ):
            await computer.run("sleep 1000")

    @pytest.mark.usefixtures("mock_env")
    async def test_run_raises_cli_error_on_other_failure(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() raises CLIError on unexpected failures."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        mock_sandbox.commands.run.side_effect = Exception("Network error")

        with (
            patch.dict(sys.modules, {"e2b": mock_e2b_module}),
            pytest.raises(CLIError, match="Command execution failed"),
        ):
            await computer.run("echo hello")

    @pytest.mark.usefixtures("mock_env")
    async def test_run_uses_default_timeout(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() uses default timeout when not specified."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            await computer.run("echo hello")

            # Default is 120000ms = 120s
            mock_sandbox.commands.run.assert_called_once_with("echo hello", timeout=120)

    @pytest.mark.usefixtures("mock_env")
    async def test_run_respects_timeout_parameter(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() respects custom timeout in milliseconds."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            await computer.run("echo hello", timeout=_CUSTOM_TIMEOUT_MS)

            mock_sandbox.commands.run.assert_called_once_with("echo hello", timeout=5)

    @pytest.mark.usefixtures("mock_env")
    async def test_run_caps_timeout_at_max(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test run() caps timeout at BASH_MAX_TIMEOUT_MS."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            # Request 1 hour, but max is 600000ms (10 min)
            await computer.run("echo hello", timeout=_ONE_HOUR_MS)

            mock_sandbox.commands.run.assert_called_once_with("echo hello", timeout=600)  # 600s = 10 min


class TestEnsureSandboxReady:
    """Tests for _ensure_sandbox_ready()."""

    @pytest.mark.usefixtures("mock_env")
    async def test_noop_when_enough_time(self, mock_sandbox: MagicMock) -> None:
        """Test no action when sandbox has enough time remaining."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        # 5 minutes remaining, need 2 minutes + buffer
        info = MagicMock()
        info.started_at = datetime.now(UTC) - timedelta(seconds=60)
        info.end_at = datetime.now(UTC) + timedelta(seconds=300)
        mock_sandbox.get_info.return_value = info

        await computer._ensure_sandbox_ready(command_timeout_s=60)

        mock_sandbox.set_timeout.assert_not_called()
        mock_sandbox.beta_pause.assert_not_called()

    @pytest.mark.usefixtures("mock_env")
    async def test_extends_timeout_when_within_limit(self, mock_sandbox: MagicMock) -> None:
        """Test extends timeout when within E2B's 1hr limit."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        # Only 30s remaining, need 2 min + buffer
        info = MagicMock()
        info.started_at = datetime.now(UTC) - timedelta(seconds=60)
        info.end_at = datetime.now(UTC) + timedelta(seconds=30)
        mock_sandbox.get_info.return_value = info

        await computer._ensure_sandbox_ready(command_timeout_s=120)

        mock_sandbox.set_timeout.assert_called_once_with(SANDBOX_DEFAULT_LIFETIME_S)

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_resume_when_exceeds_limit(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test pause/resume when extending would exceed 1hr limit."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._sandbox_id = "sandbox-123"
        computer._is_paused = False

        # Sandbox has been running for 55 minutes, only 30s left
        # Extending by 600s would exceed 1hr limit
        info = MagicMock()
        info.started_at = datetime.now(UTC) - timedelta(seconds=_E2B_MAX_LIFETIME_S - 300)  # 55 min ago
        info.end_at = datetime.now(UTC) + timedelta(seconds=30)
        mock_sandbox.get_info.return_value = info

        new_sandbox = MagicMock()
        new_sandbox.sandbox_id = "sandbox-123"
        mock_e2b_module.AsyncSandbox.connect = AsyncMock(return_value=new_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            await computer._ensure_sandbox_ready(command_timeout_s=120)

            mock_sandbox.beta_pause.assert_called_once()
            mock_e2b_module.AsyncSandbox.connect.assert_called_once()

    @pytest.mark.usefixtures("mock_env")
    async def test_handles_get_info_failure(self, mock_sandbox: MagicMock) -> None:
        """Test continues when get_info fails."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        mock_sandbox.get_info.side_effect = Exception("API error")

        # Should not raise, just continue
        await computer._ensure_sandbox_ready(command_timeout_s=60)


class TestPauseAndResume:
    """Tests for _pause_and_resume()."""

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_and_resume_resets_timer(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test pause and resume resets the sandbox timer."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._sandbox_id = "sandbox-123"
        computer._is_paused = False

        new_sandbox = MagicMock()
        new_sandbox.sandbox_id = "sandbox-123"
        mock_e2b_module.AsyncSandbox.connect = AsyncMock(return_value=new_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            await computer._pause_and_resume()

            mock_sandbox.beta_pause.assert_called_once()
            mock_e2b_module.AsyncSandbox.connect.assert_called_once_with("sandbox-123", timeout=SANDBOX_DEFAULT_LIFETIME_S)
            assert computer._sandbox is new_sandbox
            assert not computer._is_paused

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_and_resume_raises_on_pause_failure(self, mock_sandbox: MagicMock) -> None:
        """Test raises CLIError when pause fails."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._is_paused = False

        mock_sandbox.beta_pause.side_effect = Exception("Pause failed")

        with pytest.raises(CLIError, match="Failed to pause sandbox for timer reset"):
            await computer._pause_and_resume()

    @pytest.mark.usefixtures("mock_env")
    async def test_pause_and_resume_raises_on_resume_failure(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test raises CLIError when resume fails."""
        computer = RemoteE2BComputer()
        computer._sandbox = mock_sandbox
        computer._sandbox_id = "sandbox-123"
        computer._is_paused = False

        mock_e2b_module.AsyncSandbox.connect = AsyncMock(side_effect=Exception("Resume failed"))

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            with pytest.raises(CLIError, match="Failed to resume sandbox after pause"):
                await computer._pause_and_resume()

            # State should be cleared
            assert computer._sandbox is None
            assert computer._sandbox_id is None


class TestContextManager:
    """Tests for async context manager support."""

    @pytest.mark.usefixtures("mock_env")
    async def test_context_manager_starts_and_stops(self, mock_sandbox: MagicMock, mock_e2b_module: MagicMock) -> None:
        """Test async with starts and stops sandbox."""
        mock_e2b_module.AsyncSandbox.create = AsyncMock(return_value=mock_sandbox)

        with patch.dict(sys.modules, {"e2b": mock_e2b_module}):
            async with RemoteE2BComputer() as computer:
                assert computer._sandbox is mock_sandbox

            mock_sandbox.beta_pause.assert_called_once()


class TestProtocolCompliance:
    """Tests for Computer protocol compliance."""

    @pytest.mark.usefixtures("mock_env")
    def test_satisfies_computer_protocol(self) -> None:
        """Test RemoteE2BComputer satisfies Computer protocol."""
        from openagent.computer import Computer

        computer = RemoteE2BComputer()
        assert isinstance(computer, Computer)
