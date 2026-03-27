"""Tests for BashTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hexagent.computer import LocalNativeComputer
from hexagent.exceptions import CLIError
from hexagent.tasks import TaskRegistry
from hexagent.tools import BashTool
from hexagent.types import CLIResult

# AsyncMock GC can trigger false "coroutine was never awaited" warnings
# when mock cleanup encounters coroutine references from background tasks.
# The coroutines ARE properly awaited inside TaskRegistry._run().
pytestmark = pytest.mark.filterwarnings(
    "ignore:coroutine 'BashTool._run_background' was never awaited:RuntimeWarning",
)


class TestBashTool:
    """Tests for BashTool."""

    async def test_execute(self) -> None:
        """Execute a simple command."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="echo hello", description="test")
        assert result.output is not None
        assert "hello" in result.output

    async def test_failed_command_returns_error(self) -> None:
        """Failed command returns error in result."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="exit 1", description="test")
        assert result.error is not None


class TestBashToolOutputFormat:
    """Tests for BashTool output/error formatting."""

    async def test_success_output_only(self) -> None:
        """Successful command with only stdout sets output."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="echo hello", description="test")
        assert result.output == "hello"
        assert result.error is None

    async def test_success_with_stderr_includes_both(self) -> None:
        """Successful command with stderr appends it to output."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="echo out && echo warn >&2", description="test")
        assert result.output is not None
        assert "out" in result.output
        assert "warn" in result.output
        assert result.error is None

    async def test_success_empty_output(self) -> None:
        """Successful command with no output returns empty string."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="true", description="test")
        assert result.output == ""
        assert result.error is None

    async def test_failure_includes_exit_code(self) -> None:
        """Failed command error includes exit code."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="exit 42", description="test")
        assert result.error is not None
        assert "Exit code 42" in result.error
        assert result.output is None

    async def test_failure_includes_stderr(self) -> None:
        """Failed command error includes stderr."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="echo errmsg >&2; exit 1", description="test")
        assert result.error is not None
        assert "errmsg" in result.error

    async def test_failure_includes_stdout(self) -> None:
        """Failed command error includes stdout after stderr."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="echo partial; echo fail >&2; exit 1", description="test")
        assert result.error is not None
        assert "partial" in result.error
        assert "fail" in result.error

    async def test_failure_output_is_none(self) -> None:
        """Failed command never sets output (mutually exclusive)."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="echo something; exit 1", description="test")
        assert result.output is None
        assert result.error is not None


class TestBashToolCLIError:
    """Tests for BashTool handling of CLIError (infrastructure failures)."""

    async def test_cli_error_returns_error_result(self) -> None:
        """CLIError from computer.run is caught and returned as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("sandbox crashed"))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="anything", description="test")
        assert result.error is not None
        assert "sandbox crashed" in result.error

    async def test_cli_error_includes_system_message(self) -> None:
        """CLIError result includes a system message for the agent."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("timeout"))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="anything", description="test")
        assert result.system is not None

    async def test_cli_error_output_is_none(self) -> None:
        """CLIError result has no output."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("boom"))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="anything", description="test")
        assert result.output is None


class TestBashToolBackground:
    """Tests for BashTool background execution."""

    async def test_background_returns_task_id(self) -> None:
        """run_in_background=True returns immediately with task_id."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        result = await tool(command="echo bg", description="test bg", run_in_background=True)
        assert result.output is not None
        assert len(registry._tasks) == 1
        await registry.cancel_all()

    async def test_background_task_completes(self) -> None:
        """Background command completes and stores result."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="echo background", description="test bg", run_in_background=True)
        task_id = next(iter(registry._tasks.keys()))
        entry = await registry.wait(task_id, timeout_ms=5000)
        assert entry.status == "completed"
        assert entry.result is not None
        assert "background" in entry.result.output  # type: ignore[operator]
        await registry.cancel_all()

    async def test_background_task_cancel(self) -> None:
        """Background command can be cancelled."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="sleep 999", description="long sleep", run_in_background=True)
        task_id = next(iter(registry._tasks.keys()))
        entry = await registry.cancel(task_id)
        assert entry.status == "cancelled"

    async def test_background_failed_command(self) -> None:
        """Background command with non-zero exit is completed (not failed)."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="exit 1", description="fail cmd", run_in_background=True)
        task_id = next(iter(registry._tasks.keys()))
        entry = await registry.wait(task_id, timeout_ms=5000)
        assert entry.status == "completed"
        assert entry.result is not None
        assert entry.result.error is not None
        await registry.cancel_all()

    async def test_background_cli_error(self) -> None:
        """CLIError in background yields completed status with error in result."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("infra error"))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="anything", description="cli err", run_in_background=True)
        task_id = next(iter(registry._tasks.keys()))
        entry = await registry.wait(task_id, timeout_ms=5000)
        assert entry.status == "completed"
        assert entry.result is not None
        assert "infra error" in entry.result.error  # type: ignore[operator]
        await registry.cancel_all()

    async def test_background_no_timeout(self) -> None:
        """Background command without timeout calls computer.run with timeout=None."""
        computer = AsyncMock()
        computer.run = AsyncMock(return_value=CLIResult(stdout="ok", exit_code=0))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="echo test", description="no timeout", run_in_background=True)
        # Wait for background task to complete
        task_id = next(iter(registry._tasks.keys()))
        await registry.wait(task_id, timeout_ms=5000)
        computer.run.assert_called_once_with("echo test", timeout=None)
        await registry.cancel_all()

    async def test_background_with_timeout(self) -> None:
        """Background command with timeout passes it to computer.run."""
        computer = AsyncMock()
        computer.run = AsyncMock(return_value=CLIResult(stdout="ok", exit_code=0))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="echo test", description="with timeout", run_in_background=True, timeout=30000)
        task_id = next(iter(registry._tasks.keys()))
        await registry.wait(task_id, timeout_ms=5000)
        computer.run.assert_called_once_with("echo test", timeout=30000)
        await registry.cancel_all()

    async def test_foreground_default_timeout(self) -> None:
        """Foreground command without timeout uses 120000ms default."""
        computer = AsyncMock()
        computer.run = AsyncMock(return_value=CLIResult(stdout="ok", exit_code=0))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="echo test", description="default timeout")
        computer.run.assert_called_once_with("echo test", timeout=120_000)

    async def test_foreground_explicit_timeout(self) -> None:
        """Foreground command with explicit timeout passes it through."""
        computer = AsyncMock()
        computer.run = AsyncMock(return_value=CLIResult(stdout="ok", exit_code=0))
        registry = TaskRegistry()
        tool = BashTool(computer, registry)
        await tool(command="echo test", description="explicit timeout", timeout=5000)
        computer.run.assert_called_once_with("echo test", timeout=5000)
