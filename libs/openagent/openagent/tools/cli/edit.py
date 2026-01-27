"""Edit tool for performing string replacements in files.

This module provides the EditTool class that enables agents to perform
exact string replacements in files through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import EditToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer


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
