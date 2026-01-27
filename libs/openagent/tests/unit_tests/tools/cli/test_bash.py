"""Tests for BashTool."""

from openagent.computer import LocalNativeComputer
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
