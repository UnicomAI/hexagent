"""Bash tool for executing shell commands.

This module provides the BashTool class that enables agents to execute
arbitrary bash commands through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.tools.base import BaseAgentTool
from openagent.types import BashToolParams, ToolResult

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
