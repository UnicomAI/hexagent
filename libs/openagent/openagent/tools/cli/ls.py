"""LS tool for listing directory contents.

This module provides the LSTool class that enables agents to list
directory contents through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import LSToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer


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
