"""Tests for TodoWriteTool."""

from __future__ import annotations

from typing import Literal

from clawwork.tools.todo.todowrite import TodoWriteTool
from clawwork.types import TodoItem, TodoWriteToolParams


def _params(items: list[TodoItem]) -> TodoWriteToolParams:
    return TodoWriteToolParams(todos=items)


def _item(
    content: str,
    status: Literal["pending", "in_progress", "completed"] = "pending",
) -> TodoItem:
    return TodoItem(content=content, status=status, active_form=content)


class TestTodoWriteTool:
    """Tests for TodoWriteTool.execute()."""

    async def test_write_single_pending_item(self) -> None:
        tool = TodoWriteTool()
        result = await tool.execute(_params([_item("task A")]))

        assert result.output is not None
        assert "1 item(s)" in result.output
        assert "0 completed" in result.output
        assert "1 pending" in result.output

    async def test_write_mixed_statuses(self) -> None:
        tool = TodoWriteTool()
        result = await tool.execute(
            _params(
                [
                    _item("done", "completed"),
                    _item("wip", "in_progress"),
                    _item("todo", "pending"),
                ]
            )
        )

        assert result.output is not None
        assert "3 item(s)" in result.output
        assert "1 completed" in result.output
        assert "1 in progress" in result.output
        assert "1 pending" in result.output

    async def test_clear_with_empty_list(self) -> None:
        tool = TodoWriteTool()
        # Write some items first
        await tool.execute(_params([_item("task")]))
        # Then clear
        result = await tool.execute(_params([]))

        assert result.output == "Todo list cleared."
        assert tool.todos == []

    async def test_replaces_previous_list(self) -> None:
        tool = TodoWriteTool()
        await tool.execute(_params([_item("old task")]))
        await tool.execute(_params([_item("new task", "completed")]))

        assert len(tool.todos) == 1
        assert tool.todos[0].content == "new task"
        assert tool.todos[0].status == "completed"

    async def test_todos_property_returns_copy(self) -> None:
        tool = TodoWriteTool()
        await tool.execute(_params([_item("task")]))

        copy = tool.todos
        copy.clear()

        assert len(tool.todos) == 1, "Mutating returned list should not affect internal state"

    async def test_all_completed(self) -> None:
        tool = TodoWriteTool()
        result = await tool.execute(_params([_item("a", "completed"), _item("b", "completed")]))

        assert result.output is not None
        assert "2 completed" in result.output
        assert "0 in progress" in result.output
        assert "0 pending" in result.output

    async def test_all_in_progress(self) -> None:
        tool = TodoWriteTool()
        result = await tool.execute(_params([_item("a", "in_progress"), _item("b", "in_progress")]))

        assert result.output is not None
        assert "0 completed" in result.output
        assert "2 in progress" in result.output
        assert "0 pending" in result.output
