"""Tests for hexagent.tasks — TaskRegistry."""

# ruff: noqa: PT018

from __future__ import annotations

import asyncio

import pytest

from hexagent.tasks import TaskRegistry
from hexagent.types import ToolResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _success_coro(output: str = "done", delay: float = 0.0) -> ToolResult:
    if delay > 0:
        await asyncio.sleep(delay)
    return ToolResult(output=output)


async def _failing_coro(error_msg: str = "boom", delay: float = 0.0) -> ToolResult:
    if delay > 0:
        await asyncio.sleep(delay)
    raise RuntimeError(error_msg)


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------


class TestSubmit:
    async def test_creates_running_entry(self, task_registry: TaskRegistry) -> None:
        task_registry.submit("t1", "test", "desc", _success_coro(delay=1.0))
        entry = task_registry.get("t1")
        assert entry is not None
        assert entry.status == "running"

    async def test_completes_successfully(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro("hello"))
        entry = await registry.wait("t1", timeout_ms=5000)
        assert entry.status == "completed"
        assert entry.result is not None
        assert entry.result.output == "hello"
        assert entry.result.error is None

    async def test_captures_failure(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _failing_coro("test error"))
        entry = await registry.wait("t1", timeout_ms=5000)
        assert entry.status == "failed"
        assert entry.result is not None
        assert entry.result.error is not None

    async def test_raises_on_running_duplicate(self, task_registry: TaskRegistry) -> None:
        task_registry.submit("t1", "test", "desc", _success_coro(delay=10.0))
        with pytest.raises(RuntimeError):
            task_registry.submit("t1", "test", "desc2", _success_coro())

    async def test_resets_terminal_entry(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "first", _success_coro("first"))
        await registry.wait("t1", timeout_ms=5000)
        assert registry.get("t1") is not None
        assert registry.get("t1").status == "completed"  # type: ignore[union-attr]

        # Resubmit same ID with a new coro
        registry.submit("t1", "test", "second", _success_coro("second"))
        entry = await registry.wait("t1", timeout_ms=5000)
        assert entry.status == "completed"
        assert entry.result is not None
        assert entry.result.output == "second"


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------


class TestRegister:
    async def test_creates_entry_without_asyncio_task(self) -> None:
        registry = TaskRegistry()
        entry = registry.register("r1", "agent", "foreground task")
        assert entry.asyncio_task is None
        assert entry.status == "running"
        assert entry.task_id == "r1"

    async def test_raises_on_running_duplicate(self) -> None:
        registry = TaskRegistry()
        registry.register("r1", "agent", "task")
        with pytest.raises(RuntimeError):
            registry.register("r1", "agent", "task again")

    async def test_resets_terminal_entry(self) -> None:
        registry = TaskRegistry()
        registry.register("r1", "agent", "first")
        registry.complete("r1", ToolResult(output="done"))

        entry = registry.register("r1", "agent", "second")
        assert entry.status == "running"
        assert entry.result is None
        assert entry.asyncio_task is None


# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------


class TestComplete:
    async def test_sets_terminal_state(self) -> None:
        registry = TaskRegistry()
        registry.register("c1", "agent", "task")
        registry.complete("c1", ToolResult(output="fg result"))

        entry = registry.get("c1")
        assert entry is not None
        assert entry.status == "completed"
        assert entry.result is not None
        assert entry.result.output == "fg result"
        assert entry.completion_event.is_set()

    async def test_does_not_add_to_completions(self) -> None:
        registry = TaskRegistry()
        registry.register("c1", "agent", "task")
        registry.complete("c1", ToolResult(output="fg result"))

        completions = registry.drain_completions()
        assert len(completions) == 0

    async def test_raises_on_unknown(self) -> None:
        registry = TaskRegistry()
        with pytest.raises(KeyError):
            registry.complete("nope", ToolResult(output="x"))

    async def test_raises_on_not_running(self) -> None:
        registry = TaskRegistry()
        registry.register("c1", "agent", "task")
        registry.complete("c1", ToolResult(output="done"))
        with pytest.raises(RuntimeError):
            registry.complete("c1", ToolResult(output="again"))


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


class TestGet:
    async def test_unknown_returns_none(self) -> None:
        registry = TaskRegistry()
        assert registry.get("nonexistent") is None


# ---------------------------------------------------------------------------
# Wait
# ---------------------------------------------------------------------------


class TestWait:
    async def test_returns_completed_entry(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro("result"))
        entry = await registry.wait("t1", timeout_ms=5000)
        assert entry.status == "completed"

    async def test_unknown_raises_key_error(self) -> None:
        registry = TaskRegistry()
        with pytest.raises(KeyError):
            await registry.wait("nope", timeout_ms=100)

    async def test_timeout_raises_timeout_error(self, task_registry: TaskRegistry) -> None:
        task_registry.submit("t1", "test", "desc", _success_coro(delay=10.0))
        with pytest.raises(TimeoutError):
            await task_registry.wait("t1", timeout_ms=50)


# ---------------------------------------------------------------------------
# Drain completions
# ---------------------------------------------------------------------------


class TestDrainCompletions:
    async def test_returns_completions_and_clears(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "a task", _success_coro("ok"))
        await registry.wait("t1", timeout_ms=5000)

        completions = registry.drain_completions()
        assert len(completions) == 1
        assert completions[0].task_id == "t1"
        assert completions[0].status == "completed"
        assert completions[0].result.output == "ok"

    async def test_failed_task_appears(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "fail task", _failing_coro("bad"))
        await registry.wait("t1", timeout_ms=5000)

        completions = registry.drain_completions()
        assert len(completions) == 1
        assert completions[0].status == "failed"

    async def test_cancelled_task_does_not_appear(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "cancel me", _success_coro(delay=10.0))
        await registry.cancel("t1")

        completions = registry.drain_completions()
        assert len(completions) == 0

    async def test_second_drain_is_empty(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "desc", _success_coro())
        await registry.wait("t1", timeout_ms=5000)

        first = registry.drain_completions()
        assert len(first) == 1
        second = registry.drain_completions()
        assert len(second) == 0


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


class TestCancel:
    async def test_cancels_running_task(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "cancel me", _success_coro(delay=10.0))
        entry = await registry.cancel("t1")
        assert entry.status == "cancelled"
        assert entry.result is not None
        assert entry.result.error is not None

    async def test_cancel_completed_is_noop(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "done", _success_coro())
        await registry.wait("t1", timeout_ms=5000)
        entry = await registry.cancel("t1")
        assert entry.status == "completed"

    async def test_cancel_unknown_raises_key_error(self) -> None:
        registry = TaskRegistry()
        with pytest.raises(KeyError):
            await registry.cancel("nope")


# ---------------------------------------------------------------------------
# Cancel all
# ---------------------------------------------------------------------------


class TestCancelAll:
    async def test_cancels_multiple_running_tasks(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "t1", _success_coro(delay=10.0))
        registry.submit("t2", "test", "t2", _success_coro(delay=10.0))
        await registry.cancel_all()

        e1 = registry.get("t1")
        e2 = registry.get("t2")
        assert e1 is not None and e1.status == "cancelled"
        assert e2 is not None and e2.status == "cancelled"

    async def test_cancel_all_does_not_queue_completions(self) -> None:
        registry = TaskRegistry()
        registry.submit("t1", "test", "t1", _success_coro(delay=10.0))
        registry.submit("t2", "test", "t2", _success_coro(delay=10.0))
        await registry.cancel_all()

        completions = registry.drain_completions()
        assert len(completions) == 0

    async def test_noop_with_no_tasks(self) -> None:
        registry = TaskRegistry()
        await registry.cancel_all()  # should not raise
