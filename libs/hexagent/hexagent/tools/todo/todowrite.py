"""TodoWrite tool for managing a todo list.

This module provides the TodoWriteTool class that enables agents to
track and update a list of todo items with status tracking.
"""

from __future__ import annotations

from typing import Literal

from hexagent.tools.base import BaseAgentTool
from hexagent.types import TodoItem, TodoWriteToolParams, ToolResult


class TodoWriteTool(BaseAgentTool[TodoWriteToolParams]):
    """Tool for writing/updating the agent's todo list.

    Replaces the current todo list with the provided items, enabling
    the agent to track task progress during complex workflows.

    Attributes:
        name: Tool name for API registration.
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["TodoWrite"] = "TodoWrite"
    description: str = "Write and update the todo list for tracking task progress."
    args_schema = TodoWriteToolParams

    def __init__(self) -> None:
        """Initialize the TodoWriteTool."""
        self._todos: list[TodoItem] = []

    @property
    def todos(self) -> list[TodoItem]:
        """Return the current todo list."""
        return list(self._todos)

    async def execute(self, params: TodoWriteToolParams) -> ToolResult:
        """Update the todo list.

        Args:
            params: Validated parameters containing the todo items.

        Returns:
            ToolResult with a summary of the updated todo list.
        """
        self._todos = list(params.todos)

        total = len(self._todos)
        if total == 0:
            return ToolResult(output="Todo list cleared.")

        by_status: dict[str, int] = {"pending": 0, "in_progress": 0, "completed": 0}
        for item in self._todos:
            by_status[item.status] += 1

        summary = (
            f"Todo list updated: {total} item(s) — "
            f"{by_status['completed']} completed, "
            f"{by_status['in_progress']} in progress, "
            f"{by_status['pending']} pending."
        )
        return ToolResult(output=summary)
