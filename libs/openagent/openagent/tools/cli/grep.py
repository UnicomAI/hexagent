"""Grep tool for searching file contents.

This module provides the GrepTool class that enables agents to search
for patterns in files through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import GrepToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer


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
