"""CLI tools for interacting with a computer through the command line.

This module provides tools that use a Computer to give agents the ability
to interact with a computer via shell commands and file operations.

Tools provided:
- BashTool: Execute arbitrary bash commands
- ReadTool: Read file contents with line numbers
- WriteTool: Create or overwrite files
- EditTool: Perform string replacements in files
- GlobTool: Find files by pattern
- GrepTool: Search for patterns in files

Factory functions:
- create_bash_tool: Create the bash tool
- create_filesystem_tools: Create file operation tools (read, write, edit, glob, grep)
- create_cli_tools: Create all CLI tools sharing a Computer instance
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from openagent.tools.cli.bash import BashTool
from openagent.tools.cli.edit import EditTool
from openagent.tools.cli.glob import GlobTool
from openagent.tools.cli.grep import GrepTool
from openagent.tools.cli.read import ReadTool
from openagent.tools.cli.write import WriteTool

if TYPE_CHECKING:
    from openagent.computer import Computer
    from openagent.tools.base import BaseAgentTool


def create_bash_tool(computer: Computer) -> BashTool:
    """Create a bash tool for executing shell commands.

    Args:
        computer: The Computer instance to execute commands on.

    Returns:
        BashTool instance.

    Example:
        ```python
        from openagent.computer import LocalComputer
        from openagent.tools.cli import create_bash_tool

        computer = LocalComputer()
        bash = create_bash_tool(computer)
        result = await bash(command="echo hello")
        ```
    """
    return BashTool(computer)


def create_filesystem_tools(computer: Computer) -> list[BaseAgentTool[Any]]:
    """Create file operation tools (read, write, edit, glob, grep).

    These tools provide file system operations through the Computer interface.
    All tools share the same Computer instance, so state persists across calls.

    Args:
        computer: The Computer instance all tools will share.

    Returns:
        List of tool instances:
        [ReadTool, WriteTool, EditTool, GlobTool, GrepTool]

    Example:
        ```python
        from openagent.computer import LocalComputer
        from openagent.tools.cli import create_filesystem_tools

        computer = LocalComputer()
        fs_tools = create_filesystem_tools(computer)

        # Find the read tool
        read_tool = next(t for t in fs_tools if t.name == "read")
        result = await read_tool(file_path="/etc/hosts")
        ```
    """
    return [
        ReadTool(computer),
        WriteTool(computer),
        EditTool(computer),
        GlobTool(computer),
        GrepTool(computer),
    ]


def create_cli_tools(computer: Computer) -> list[BaseAgentTool[Any]]:
    """Create all CLI tools sharing a single Computer instance.

    Convenience function that combines create_bash_tool and create_filesystem_tools.
    Creates a complete set of tools (bash, read, write, edit, glob, grep)
    that operate on the provided Computer.

    Args:
        computer: The Computer instance all tools will share.

    Returns:
        List of tool instances:
        [BashTool, ReadTool, WriteTool, EditTool, GlobTool, GrepTool]

    Example:
        ```python
        from openagent.computer import LocalComputer
        from openagent.tools.cli import create_cli_tools

        computer = LocalComputer()
        tools = create_cli_tools(computer)

        # Use individual tools
        bash_tool = tools[0]
        result = await bash_tool(command="echo hello")
        ```
    """
    return [create_bash_tool(computer), *create_filesystem_tools(computer)]


__all__ = [
    "BashTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
    "ReadTool",
    "WriteTool",
    "create_bash_tool",
    "create_cli_tools",
    "create_filesystem_tools",
]
