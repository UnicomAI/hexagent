"""Computer tool implementations for executing commands and file operations.

This module provides tools that use a Computer to give agents the ability
to interact with a computer via shell commands and file operations.

Tools provided:
- BashTool: Execute arbitrary bash commands
- ReadTool: Read file contents with line numbers (TODO: implement)
- WriteTool: Create or overwrite files (TODO: implement)
- EditTool: Perform string replacements in files (TODO: implement)
- LSTool: List directory contents (TODO: implement)
- GlobTool: Find files by pattern (TODO: implement)
- GrepTool: Search for patterns in files (TODO: implement)

Factory functions:
- create_bash_tool: Create the bash tool
- create_filesystem_tools: Create file operation tools (read, write, edit, ls, glob, grep)
- create_computer_tools: Create all computer tools sharing a Computer instance
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import (
    BashToolParams,
    EditToolParams,
    GlobToolParams,
    GrepToolParams,
    LSToolParams,
    ReadToolParams,
    ToolResult,
    WriteToolParams,
)

if TYPE_CHECKING:
    from openagent.computer import Computer


class BashTool(BaseAgentTool[BashToolParams]):
    """Tool for executing bash commands on a Computer.

    Features:
    - Commands auto-start the computer if not running
    - State persists within the computer session (cwd, env vars)

    Attributes:
        name: Tool name for API registration ("bash").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.

    Examples:
        Basic usage:
        ```python
        computer = LocalNativeComputer()
        tool = BashTool(computer)
        result = await tool(command="echo hello")
        print(result.output)  # "hello"
        ```
    """

    name: Literal["bash"] = "bash"
    description: str = "Execute bash commands. Each command runs in a fresh process."
    args_schema = BashToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the BashTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: BashToolParams) -> ToolResult:
        """Execute a bash command.

        Args:
            params: Validated parameters containing command.

        Returns:
            ToolResult with output from the command.
        """
        result = await self._computer.run(params.command)

        # Convert CLIResult to ToolResult
        if result.exit_code != 0:
            error_msg = result.stderr or result.stdout or f"Command failed with exit code {result.exit_code}"
            return ToolResult(error=error_msg)

        return ToolResult(output=result.stdout or "")


class ReadTool(BaseAgentTool[ReadToolParams]):
    r"""Tool for reading file contents with line numbers.

    TODO: Implement this tool.

    Attributes:
        name: Tool name for API registration ("read").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["read"] = "read"
    description: str = "Read file contents with line numbers. Returns cat -n format. Binary files rejected."
    args_schema = ReadToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the ReadTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: ReadToolParams) -> ToolResult:
        """Read a file's contents with line numbers.

        Args:
            params: Validated parameters containing file_path, offset, and limit.

        Returns:
            ToolResult with numbered file contents (cat -n format).
        """
        msg = "ReadTool is not yet implemented"
        raise NotImplementedError(msg)


class WriteTool(BaseAgentTool[WriteToolParams]):
    """Tool for writing content to files.

    TODO: Implement this tool.

    Attributes:
        name: Tool name for API registration ("write").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["write"] = "write"
    description: str = "Write content to a file. Creates parent directories as needed."
    args_schema = WriteToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the WriteTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: WriteToolParams) -> ToolResult:
        """Write content to a file.

        Args:
            params: Validated parameters containing file_path and content.

        Returns:
            ToolResult with success message or error.
        """
        msg = "WriteTool is not yet implemented"
        raise NotImplementedError(msg)


class EditTool(BaseAgentTool[EditToolParams]):
    """Tool for performing string replacements in files.

    TODO: Implement this tool.

    Attributes:
        name: Tool name for API registration ("edit").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["edit"] = "edit"
    description: str = "Perform exact string replacement in a file."
    args_schema = EditToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the EditTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: EditToolParams) -> ToolResult:
        """Replace a string in a file.

        Args:
            params: Validated parameters containing file_path, old_string,
                new_string, and replace_all flag.

        Returns:
            ToolResult with success message or error.
        """
        msg = "EditTool is not yet implemented"
        raise NotImplementedError(msg)


class LSTool(BaseAgentTool[LSToolParams]):
    """Tool for listing directory contents.

    TODO: Implement this tool.

    Attributes:
        name: Tool name for API registration ("ls").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["ls"] = "ls"
    description: str = "List directory contents with ls -la."
    args_schema = LSToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the LSTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: LSToolParams) -> ToolResult:
        """List directory contents.

        Args:
            params: Validated parameters containing path.

        Returns:
            ToolResult with ls -la output.
        """
        msg = "LSTool is not yet implemented"
        raise NotImplementedError(msg)


class GlobTool(BaseAgentTool[GlobToolParams]):
    r"""Tool for finding files by pattern.

    TODO: Implement this tool.

    Attributes:
        name: Tool name for API registration ("glob").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["glob"] = "glob"
    description: str = "Find files matching a glob pattern. Max 100 results."
    args_schema = GlobToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the GlobTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: GlobToolParams) -> ToolResult:
        """Find files matching a glob pattern, sorted by modification time.

        Args:
            params: Validated parameters containing pattern and path.

        Returns:
            ToolResult with matching file paths sorted by mtime (most recent first),
            one per line.
        """
        msg = "GlobTool is not yet implemented"
        raise NotImplementedError(msg)


class GrepTool(BaseAgentTool[GrepToolParams]):
    """Tool for searching file contents.

    TODO: Implement this tool.

    Attributes:
        name: Tool name for API registration ("grep").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["grep"] = "grep"
    description: str = "Search for regex patterns in files. Max 100 results."
    args_schema = GrepToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the GrepTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: GrepToolParams) -> ToolResult:
        """Search for a pattern in files.

        Args:
            params: Validated parameters containing pattern, path, glob, output_mode,
                and additional options like type, case_insensitive, context lines, etc.

        Returns:
            ToolResult with search results based on output_mode.
        """
        msg = "GrepTool is not yet implemented"
        raise NotImplementedError(msg)


def create_bash_tool(computer: Computer) -> BashTool:
    """Create a bash tool for executing shell commands.

    Args:
        computer: The Computer instance to execute commands on.

    Returns:
        BashTool instance.

    Example:
        ```python
        from openagent.computer import LocalComputer
        from openagent.tools import create_bash_tool

        computer = LocalComputer()
        bash = create_bash_tool(computer)
        result = await bash(command="echo hello")
        ```
    """
    return BashTool(computer)


def create_filesystem_tools(computer: Computer) -> list[BaseAgentTool[Any]]:
    """Create file operation tools (read, write, edit, ls, glob, grep).

    These tools provide file system operations through the Computer interface.
    All tools share the same Computer instance, so state persists across calls.

    NOTE: These tools are stubs and raise NotImplementedError when called.
    They are included for API completeness and will be implemented in future versions.

    Args:
        computer: The Computer instance all tools will share.

    Returns:
        List of tool instances:
        [ReadTool, WriteTool, EditTool, LSTool, GlobTool, GrepTool]

    Example:
        ```python
        from openagent.computer import LocalComputer
        from openagent.tools import create_filesystem_tools

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
        LSTool(computer),
        GlobTool(computer),
        GrepTool(computer),
    ]


def create_computer_tools(computer: Computer) -> list[BaseAgentTool[Any]]:
    """Create all computer tools sharing a single Computer instance.

    Convenience function that combines create_bash_tool and create_filesystem_tools.
    Creates a complete set of tools (bash, read, write, edit, ls, glob, grep)
    that operate on the provided Computer.

    NOTE: Only BashTool is fully implemented. Other tools are stubs and will
    raise NotImplementedError when called.

    Args:
        computer: The Computer instance all tools will share.

    Returns:
        List of tool instances:
        [BashTool, ReadTool, WriteTool, EditTool, LSTool, GlobTool, GrepTool]

    Example:
        ```python
        from openagent.computer import LocalComputer
        from openagent.tools import create_computer_tools

        computer = LocalComputer()
        tools = create_computer_tools(computer)

        # Use individual tools
        bash_tool = tools[0]
        result = await bash_tool(command="echo hello")
        ```
    """
    return [create_bash_tool(computer), *create_filesystem_tools(computer)]
