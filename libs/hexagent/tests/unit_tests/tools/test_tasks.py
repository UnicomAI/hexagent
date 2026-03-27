"""Tests for tools/tasks.py — TaskOutputTool & TaskStopTool."""

from __future__ import annotations

import asyncio

from hexagent.tasks import TaskRegistry
from hexagent.tools.task import TaskOutputTool, TaskStopTool
from hexagent.types import TaskOutputToolParams, TaskStopToolParams, ToolResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _success_coro(output: str = "done", delay: float = 0.0) -> ToolResult:
    if delay > 0:
        await asyncio.sleep(delay)
    return ToolResult(output=output)


async def _failing_coro(error_msg: str = "boom") -> ToolResult:
    raise RuntimeError(error_msg)


# ---------------------------------------------------------------------------
# TaskOutputTool
# ---------------------------------------------------------------------------


class TestTaskOutputTool:
    async def test_completed_returns_result(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro("hello"))
        await registry.wait("t1", timeout_ms=5000)

        tool = TaskOutputTool(registry)
        result = await tool.execute(TaskOutputToolParams(task_id="t1"))
        assert result.output == "hello"
        assert result.error is None

    async def test_failed_returns_error(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _failing_coro("kaboom"))
        await registry.wait("t1", timeout_ms=5000)

        tool = TaskOutputTool(registry)
        result = await tool.execute(TaskOutputToolParams(task_id="t1"))
        assert result.error is not None

    async def test_unknown_returns_error(self) -> None:
        registry = TaskRegistry()
        tool = TaskOutputTool(registry)
        result = await tool.execute(
            TaskOutputToolParams(task_id="nope", block=False, timeout=100),
        )
        assert result.error is not None

    async def test_running_block_false_returns_still_running(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro(delay=10.0))

        tool = TaskOutputTool(registry)
        result = await tool.execute(
            TaskOutputToolParams(task_id="t1", block=False),
        )
        assert result.output is not None
        assert result.error is None
        await registry.cancel_all()

    async def test_running_block_true_timeout(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro(delay=10.0))

        tool = TaskOutputTool(registry)
        result = await tool.execute(
            TaskOutputToolParams(task_id="t1", block=True, timeout=50),
        )
        assert result.output is not None
        assert result.error is None
        await registry.cancel_all()

    async def test_running_block_true_completes(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro("waited", delay=0.05))

        tool = TaskOutputTool(registry)
        result = await tool.execute(
            TaskOutputToolParams(task_id="t1", block=True, timeout=5000),
        )
        assert result.output == "waited"

    async def test_output_for_foreground_entry(self) -> None:
        registry = TaskRegistry()
        registry.register("fg1", "agent", "foreground task")
        registry.complete("fg1", ToolResult(output="fg result"))

        tool = TaskOutputTool(registry)
        result = await tool.execute(TaskOutputToolParams(task_id="fg1"))
        assert result.output == "fg result"
        assert result.error is None


# ---------------------------------------------------------------------------
# TaskStopTool
# ---------------------------------------------------------------------------


class TestTaskStopTool:
    async def test_cancel_running(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro(delay=10.0))

        tool = TaskStopTool(registry)
        result = await tool.execute(TaskStopToolParams(task_id="t1"))
        assert result.output is not None
        assert result.error is None

    async def test_cancel_completed(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro())
        await registry.wait("t1", timeout_ms=5000)

        tool = TaskStopTool(registry)
        result = await tool.execute(TaskStopToolParams(task_id="t1"))
        assert result.output is not None
        assert result.error is None

    async def test_cancel_unknown(self) -> None:
        registry = TaskRegistry()
        tool = TaskStopTool(registry)
        result = await tool.execute(TaskStopToolParams(task_id="nope"))
        assert result.error is not None
