"""Tests for CLI tools factory functions."""

from clawwork.computer import LocalNativeComputer
from clawwork.tasks import TaskRegistry
from clawwork.tools import create_cli_tools


class TestCreateCliTools:
    """Tests for create_cli_tools()."""

    def test_all_tools_share_computer(self) -> None:
        """All tools share the same computer instance."""
        computer = LocalNativeComputer()
        registry = TaskRegistry()
        tools = create_cli_tools(computer, registry)
        assert len(tools) > 0
        for tool in tools:
            assert tool._computer is computer  # type: ignore[attr-defined]
