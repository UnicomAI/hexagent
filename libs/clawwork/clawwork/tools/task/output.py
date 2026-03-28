"""TaskOutput tool — retrieve results from a background task."""

from __future__ import annotations

from typing import TYPE_CHECKING

from clawwork.tools.base import BaseAgentTool
from clawwork.types import TaskOutputToolParams, ToolResult

if TYPE_CHECKING:
    from clawwork.tasks import TaskRegistry


class TaskOutputTool(BaseAgentTool[TaskOutputToolParams]):
    """Retrieve results from a background task."""

    name: str = "TaskOutput"
    description: str = "Get the result of a background task by ID."
    args_schema = TaskOutputToolParams

    def __init__(self, registry: TaskRegistry) -> None:
        """Initialize with a task registry."""
        self._registry = registry

    async def execute(self, params: TaskOutputToolParams) -> ToolResult:
        """Execute the TaskOutput tool."""
        entry = self._registry.get(params.task_id)
        if entry is None:
            return ToolResult(error=f"Task {params.task_id!r} not found.")

        if entry.status == "running":
            if not params.block:
                return ToolResult(output=f"Task {params.task_id} is still running.")
            try:
                entry = await self._registry.wait(
                    params.task_id,
                    timeout_ms=params.timeout,
                )
            except TimeoutError:
                return ToolResult(
                    output=f"Task {params.task_id} still running after {params.timeout}ms.",
                )

        # Terminal state — pass through the full ToolResult
        assert entry.result is not None  # noqa: S101
        return entry.result
