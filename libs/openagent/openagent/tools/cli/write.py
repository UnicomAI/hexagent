"""Write tool for creating and overwriting files.

This module provides the WriteTool class that enables agents to write
content to files through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import ToolResult, WriteToolParams

if TYPE_CHECKING:
    from openagent.computer import Computer


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
