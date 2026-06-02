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

from uniharness.tools.cli.bash import BashTool
from uniharness.tools.cli.edit import EditTool
from uniharness.tools.cli.glob import GlobTool
from uniharness.tools.cli.grep import GrepTool
from uniharness.tools.cli.read import ReadTool
from uniharness.tools.cli.write import WriteTool

if TYPE_CHECKING:
    from uniharness.computer import Computer
    from uniharness.tasks import TaskRegistry
    from uniharness.tools.base import BaseAgentTool


def create_bash_tool(computer: Computer, registry: TaskRegistry) -> BashTool:
    """Create a bash tool for executing shell commands.

    Args:
        computer: The Computer instance to execute commands on.
        registry: Task registry for background execution.

    Returns:
        BashTool instance.
    """
    return BashTool(computer, registry)


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
        from uniharness.computer import LocalComputer
        from uniharness.tools.cli import create_filesystem_tools

        computer = LocalComputer()
        fs_tools = create_filesystem_tools(computer)

        # Find the read tool
        read_tool = next(t for t in fs_tools if t.name == "Read")
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


def create_cli_tools(computer: Computer, registry: TaskRegistry) -> list[BaseAgentTool[Any]]:
    """Create all CLI tools sharing a single Computer instance.

    Convenience function that combines create_bash_tool and create_filesystem_tools.

    Args:
        computer: The Computer instance all tools will share.
        registry: Task registry for background bash execution.

    Returns:
        List of tool instances:
        [BashTool, ReadTool, WriteTool, EditTool, GlobTool, GrepTool]
    """
    return [create_bash_tool(computer, registry), *create_filesystem_tools(computer)]


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
