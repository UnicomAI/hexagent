"""Tests for CLI tools factory functions."""

from openagent.computer import LocalNativeComputer
from openagent.tools import create_cli_tools


class TestCreateCliTools:
    """Tests for create_cli_tools()."""

    def test_all_tools_share_computer(self) -> None:
        """All tools share the same computer instance."""
        computer = LocalNativeComputer()
        tools = create_cli_tools(computer)
        assert len(tools) > 0
        for tool in tools:
            assert tool._computer is computer  # type: ignore[attr-defined]
