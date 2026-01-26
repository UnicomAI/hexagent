"""Tests for BashTool."""

from openagent.computer import LocalNativeComputer
from openagent.tools import BashTool, create_computer_tools


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


class TestCreateTools:
    """Tests for create_computer_tools()."""

    def test_returns_all_tools(self) -> None:
        """Returns all expected tools."""
        tools = create_computer_tools(LocalNativeComputer())
        tool_names = {t.name for t in tools}
        assert tool_names == {"bash", "read", "write", "edit", "ls", "glob", "grep"}

    def test_shares_computer(self) -> None:
        """All tools share the same computer."""
        computer = LocalNativeComputer()
        tools = create_computer_tools(computer)
        for tool in tools:
            assert tool._computer is computer  # type: ignore[attr-defined]
