"""Bash tool for executing shell commands.

This module provides the BashTool class that enables agents to execute
arbitrary bash commands through a Computer interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from openagent.exceptions import CLIError
from openagent.tools.base import BaseAgentTool
from openagent.types import BashToolParams, CLIResult, ToolResult

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
            ToolResult with output on success, or error on non-zero exit.
            Never both—output and error are mutually exclusive.
        """
        try:
            result: CLIResult = await self._computer.run(params.command)
        except CLIError as exc:
            return ToolResult(
                error=str(exc),
                system=(
                    "This error did not come from your command. Your computer's"
                    " infrastructure has failed — this is never expected and"
                    " indicates a problem only the human developer can fix."
                    " Do not retry. Stop what you are doing and report this"
                    " failure to the user."
                ),
            )

        if result.exit_code == 0:
            parts = [p for p in (result.stdout, result.stderr) if p]
            return ToolResult(output="\n".join(parts) if parts else "")

        # Non-zero exit: exit code + stderr (tightly coupled), then stdout
        error = f"Exit code {result.exit_code}"
        if result.stderr:
            error += f"\n{result.stderr}"
        if result.stdout:
            error += f"\n\n{result.stdout}"
        return ToolResult(error=error)
