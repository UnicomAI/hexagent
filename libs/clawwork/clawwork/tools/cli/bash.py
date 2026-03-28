"""Bash tool for executing shell commands.

This module provides the BashTool class that enables agents to execute
arbitrary bash commands through a Computer interface. Supports both
foreground (blocking) and background (async) execution.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING, Literal

from clawwork.exceptions import CLI_INFRA_ERROR_SYSTEM_REMINDER, CLIError
from clawwork.tools.base import BaseAgentTool
from clawwork.types import BashToolParams, CLIResult, ToolResult

if TYPE_CHECKING:
    from clawwork.computer import Computer
    from clawwork.tasks import TaskRegistry

_FOREGROUND_TIMEOUT_MS = 120_000  # 2 minutes default for foreground commands


class BashTool(BaseAgentTool[BashToolParams]):
    """Tool for executing bash commands on a Computer.

    Supports foreground (blocking) and background (non-blocking) execution.
    Background commands are managed via ``TaskRegistry`` and can be queried
    with ``TaskOutputTool`` or cancelled with ``TaskStopTool``.

    Attributes:
        name: Tool name for API registration.
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["Bash"] = "Bash"
    description: str = "Execute bash commands. Each command runs in a fresh process."
    args_schema = BashToolParams

    def __init__(self, computer: Computer, registry: TaskRegistry) -> None:
        """Initialize the BashTool.

        Args:
            computer: The Computer instance to execute commands on.
            registry: Task registry for background execution.
        """
        self._computer = computer
        self._registry = registry

    async def execute(self, params: BashToolParams) -> ToolResult:
        """Execute a bash command.

        Args:
            params: Validated parameters containing command, description,
                and optional run_in_background / timeout.

        Returns:
            ToolResult with output on success, or error on non-zero exit.
        """
        if params.run_in_background:
            return self._submit_background(params)
        return await self._run_foreground(params)

    async def _run_foreground(self, params: BashToolParams) -> ToolResult:
        """Execute a command in the foreground (blocking)."""
        timeout = params.timeout if params.timeout is not None else _FOREGROUND_TIMEOUT_MS
        try:
            result: CLIResult = await self._computer.run(params.command, timeout=timeout)
        except CLIError as exc:
            return ToolResult(error=str(exc), system=CLI_INFRA_ERROR_SYSTEM_REMINDER)
        return self._format_result(result)

    def _submit_background(self, params: BashToolParams) -> ToolResult:
        """Submit a command for background execution."""
        task_id = secrets.token_hex(8)
        self._registry.submit(
            task_id,
            "bash",
            params.description,
            self._run_background(params.command, params.timeout),
        )
        return ToolResult(
            output=f"Command running in background with ID: {task_id}",
        )

    async def _run_background(self, command: str, timeout: int | None) -> ToolResult:  # noqa: ASYNC109
        """Background coroutine submitted to TaskRegistry."""
        try:
            result: CLIResult = await self._computer.run(command, timeout=timeout)
        except CLIError as exc:
            return ToolResult(error=str(exc), system=CLI_INFRA_ERROR_SYSTEM_REMINDER)
        return self._format_result(result)

    @staticmethod
    def _format_result(result: CLIResult) -> ToolResult:
        """Format a CLIResult into a ToolResult."""
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
