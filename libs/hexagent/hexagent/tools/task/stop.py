"""TaskStop tool — cancel a running background task."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hexagent.tools.base import BaseAgentTool
from hexagent.types import TaskStopToolParams, ToolResult

if TYPE_CHECKING:
    from hexagent.tasks import TaskRegistry


class TaskStopTool(BaseAgentTool[TaskStopToolParams]):
    """Cancel a running background task."""

    name: str = "TaskStop"
    description: str = "Cancel a running background task by ID."
    args_schema = TaskStopToolParams

    def __init__(self, registry: TaskRegistry) -> None:
        """Initialize with a task registry."""
        self._registry = registry

    async def execute(self, params: TaskStopToolParams) -> ToolResult:
        """Execute the TaskStop tool."""
        try:
            entry = await self._registry.cancel(params.task_id)
        except KeyError:
            return ToolResult(error=f"Task {params.task_id!r} not found.")

        if entry.status == "cancelled":
            return ToolResult(output=f"Task {params.task_id} has been cancelled.")
        return ToolResult(
            output=f"Task {params.task_id} already {entry.status}.",
        )
