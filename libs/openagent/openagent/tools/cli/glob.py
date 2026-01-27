"""Glob tool for finding files by pattern.

This module provides the GlobTool class that enables agents to find
files matching glob patterns through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import GlobToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer


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
