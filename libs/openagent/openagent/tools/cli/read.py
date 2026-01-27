"""Read tool for reading file contents.

This module provides the ReadTool class that enables agents to read
file contents with line numbers through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import ReadToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer


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
