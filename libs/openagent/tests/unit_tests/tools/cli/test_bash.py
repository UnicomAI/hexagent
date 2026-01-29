"""Tests for BashTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

from openagent.computer import LocalNativeComputer
from openagent.exceptions import CLIError
from openagent.tools import BashTool


class TestBashTool:
    """Tests for BashTool."""

    def test_name(self) -> None:
        """BashTool name is 'bash'."""
        tool = BashTool(LocalNativeComputer())
        assert tool.name == "bash"

    async def test_execute(self) -> None:
        """Execute a simple command."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="echo hello")
        assert result.output is not None
        assert "hello" in result.output

    async def test_failed_command_returns_error(self) -> None:
        """Failed command returns error in result."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="exit 1")
        assert result.error is not None


class TestBashToolOutputFormat:
    """Tests for BashTool output/error formatting."""

    async def test_success_output_only(self) -> None:
        """Successful command with only stdout sets output."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="echo hello")
        assert result.output == "hello"
        assert result.error is None

    async def test_success_with_stderr_includes_both(self) -> None:
        """Successful command with stderr appends it to output."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="echo out && echo warn >&2")
        assert result.output is not None
        assert "out" in result.output
        assert "warn" in result.output
        assert result.error is None

    async def test_success_empty_output(self) -> None:
        """Successful command with no output returns empty string."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="true")
        assert result.output == ""
        assert result.error is None

    async def test_failure_includes_exit_code(self) -> None:
        """Failed command error includes exit code."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="exit 42")
        assert result.error is not None
        assert "Exit code 42" in result.error
        assert result.output is None

    async def test_failure_includes_stderr(self) -> None:
        """Failed command error includes stderr."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="echo errmsg >&2; exit 1")
        assert result.error is not None
        assert "errmsg" in result.error

    async def test_failure_includes_stdout(self) -> None:
        """Failed command error includes stdout after stderr."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="echo partial; echo fail >&2; exit 1")
        assert result.error is not None
        assert "partial" in result.error
        assert "fail" in result.error

    async def test_failure_output_is_none(self) -> None:
        """Failed command never sets output (mutually exclusive)."""
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="echo something; exit 1")
        assert result.output is None
        assert result.error is not None


class TestBashToolCLIError:
    """Tests for BashTool handling of CLIError (infrastructure failures)."""

    async def test_cli_error_returns_error_result(self) -> None:
        """CLIError from computer.run is caught and returned as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("sandbox crashed"))
        tool = BashTool(computer)
        result = await tool(command="anything")
        assert result.error is not None
        assert "sandbox crashed" in result.error

    async def test_cli_error_includes_system_message(self) -> None:
        """CLIError result includes a system message for the agent."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("timeout"))
        tool = BashTool(computer)
        result = await tool(command="anything")
        assert result.system is not None

    async def test_cli_error_output_is_none(self) -> None:
        """CLIError result has no output."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("boom"))
        tool = BashTool(computer)
        result = await tool(command="anything")
        assert result.output is None
