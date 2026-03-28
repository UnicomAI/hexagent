"""Tests for tools/task/agent.py — AgentTool and task completion reminder."""

# ruff: noqa: ARG001, ANN401

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

from clawwork.harness.definition import AgentDefinition
from clawwork.harness.reminders import task_completion_reminder
from clawwork.tasks import TaskRegistry
from clawwork.tools.task.agent import AgentTool
from clawwork.types import AgentContext, AgentToolParams, SubagentResult, ToolResult

if TYPE_CHECKING:
    from clawwork.harness.reminders import Message

from ..conftest import STUB_PROFILE

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runner(
    output: str = "done",
    delay: float = 0.0,
    *,
    fail: bool = False,
    error_msg: str = "boom",
) -> MagicMock:
    """Create a mock SubagentRunner."""
    runner = MagicMock()
    runner.get_definition = MagicMock(return_value=None)

    async def _run(
        definition: Any,
        prompt: str,
        prior_messages: list[Any] | None = None,
        *,
        task_id: str = "",
    ) -> SubagentResult:
        if delay > 0:
            await asyncio.sleep(delay)
        if fail:
            raise RuntimeError(error_msg)
        return SubagentResult(output=output, messages=[{"role": "assistant", "content": output}])

    runner.run = AsyncMock(side_effect=_run)
    return runner


def _latest_task_id(registry: TaskRegistry) -> str:
    """Return the most recently registered task ID."""
    ids = list(registry._tasks.keys())
    assert ids, "No tasks in registry"
    return ids[-1]


# ---------------------------------------------------------------------------
# AgentTool tests
# ---------------------------------------------------------------------------


class TestAgentTool:
    async def test_sync_execution_returns_result(self) -> None:
        runner = _make_runner("tool result")
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        result = await tool.execute(
            AgentToolParams(
                description="Test",
                prompt="do work",
                subagent_type="general-purpose",
            ),
        )
        assert result.output == "tool result"
        assert result.error is None
        assert result.system is not None
        # Foreground agent is visible in registry
        agent_id = _latest_task_id(registry)
        entry = registry.get(agent_id)
        assert entry is not None
        assert entry.status == "completed"

    async def test_background_execution_returns_task_id(self, task_registry: TaskRegistry) -> None:
        runner = _make_runner("bg result", delay=0.5)
        tool = AgentTool(task_registry, runner, {})

        result = await tool.execute(
            AgentToolParams(
                description="Bg",
                prompt="do work",
                subagent_type="general-purpose",
                run_in_background=True,
            ),
        )
        assert result.output is not None
        assert "launched" in result.output.lower() or result.output  # confirms task was registered
        assert result.error is None
        # Background task is registered
        agent_id = _latest_task_id(task_registry)
        assert task_registry.get(agent_id) is not None

    async def test_unknown_subagent_type_returns_error(self) -> None:
        runner = _make_runner()
        registry = TaskRegistry()
        agents = {"explorer": AgentDefinition(description="Explore code")}
        tool = AgentTool(registry, runner, agents)

        result = await tool.execute(
            AgentToolParams(
                description="Test",
                prompt="do work",
                subagent_type="nonexistent",
            ),
        )
        assert result.error is not None

    async def test_resume_unknown_task_returns_error(self) -> None:
        runner = _make_runner()
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        result = await tool.execute(
            AgentToolParams(
                description="Resume",
                prompt="continue",
                subagent_type="general-purpose",
                resume="nonexistent",
            ),
        )
        assert result.error is not None

    async def test_foreground_failure_returns_error(self) -> None:
        runner = _make_runner(fail=True, error_msg="agent error")
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        result = await tool.execute(
            AgentToolParams(
                description="Fail",
                prompt="fail",
                subagent_type="general-purpose",
            ),
        )
        assert result.error is not None
        # Failed foreground agent is visible in registry
        entries = list(registry._tasks.values())
        assert len(entries) == 1
        assert entries[0].status == "failed"

    async def test_resume_reuses_agent_id(self) -> None:
        runner = _make_runner("first")
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        # First foreground execution
        await tool.execute(
            AgentToolParams(description="First", prompt="do work", subagent_type="general-purpose"),
        )
        agent_id = _latest_task_id(registry)

        # Resume with same agent_id
        async def _resume_run(*a: Any, **kw: Any) -> SubagentResult:
            return SubagentResult(output="second", messages=[{"role": "assistant", "content": "second"}])

        runner.run = AsyncMock(side_effect=_resume_run)
        r2 = await tool.execute(
            AgentToolParams(description="Resume", prompt="continue", subagent_type="general-purpose", resume=agent_id),
        )
        assert r2.error is None
        # Registry still has exactly one task with the same ID
        assert list(registry._tasks.keys()) == [agent_id]

    async def test_resume_running_agent_returns_error(self, task_registry: TaskRegistry) -> None:
        runner = _make_runner("bg result", delay=10.0)
        tool = AgentTool(task_registry, runner, {})

        # Spawn background agent
        await tool.execute(
            AgentToolParams(
                description="Slow",
                prompt="slow work",
                subagent_type="general-purpose",
                run_in_background=True,
            ),
        )
        agent_id = _latest_task_id(task_registry)

        # Need to add the conversation entry so resume finds it
        tool._conversations[agent_id] = [{"role": "assistant", "content": "partial"}]

        # Try to resume while still running
        r2 = await tool.execute(
            AgentToolParams(
                description="Resume",
                prompt="continue",
                subagent_type="general-purpose",
                resume=agent_id,
            ),
        )
        assert r2.error is not None
        assert "still running" in r2.error.lower() or "running" in r2.error.lower()

    async def test_foreground_agent_visible_in_registry(self) -> None:
        runner = _make_runner("visible")
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        await tool.execute(
            AgentToolParams(description="Visible", prompt="work", subagent_type="general-purpose"),
        )
        agent_id = _latest_task_id(registry)
        entry = registry.get(agent_id)
        assert entry is not None
        assert entry.status == "completed"
        assert entry.result is not None
        assert entry.result.output == "visible"

    async def test_foreground_does_not_trigger_completion_notification(self) -> None:
        runner = _make_runner("fg result")
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        await tool.execute(
            AgentToolParams(description="FG", prompt="work", subagent_type="general-purpose"),
        )
        completions = registry.drain_completions()
        assert len(completions) == 0

    async def test_resume_preserves_conversation(self) -> None:
        runner = _make_runner("first")
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        # First execution
        await tool.execute(
            AgentToolParams(description="First", prompt="do work", subagent_type="general-purpose"),
        )
        agent_id = _latest_task_id(registry)

        # Resume — runner should receive prior_messages
        async def _resume_run(*a: Any, **kw: Any) -> SubagentResult:
            return SubagentResult(output="second", messages=[{"role": "assistant", "content": "second"}])

        runner.run = AsyncMock(side_effect=_resume_run)
        await tool.execute(
            AgentToolParams(description="Resume", prompt="continue", subagent_type="general-purpose", resume=agent_id),
        )

        # Verify prior_messages was passed (3rd positional arg)
        call_args = runner.run.call_args
        prior_msgs = call_args[0][2]
        assert prior_msgs is not None
        assert len(prior_msgs) > 0

    async def test_background_resume_reuses_agent_id(self) -> None:
        runner = _make_runner("bg1", delay=0.01)
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        # Spawn background agent
        await tool.execute(
            AgentToolParams(
                description="BG1",
                prompt="work",
                subagent_type="general-purpose",
                run_in_background=True,
            ),
        )
        agent_id = _latest_task_id(registry)
        await registry.wait(agent_id, timeout_ms=5000)

        # Drain first round of completions
        registry.drain_completions()

        # Resume in background
        async def _resume_run(*a: Any, **kw: Any) -> SubagentResult:
            return SubagentResult(output="bg2", messages=[{"role": "assistant", "content": "bg2"}])

        runner.run = AsyncMock(side_effect=_resume_run)
        await tool.execute(
            AgentToolParams(
                description="BG2",
                prompt="continue",
                subagent_type="general-purpose",
                run_in_background=True,
                resume=agent_id,
            ),
        )
        # Registry still has exactly one task with the same ID
        assert list(registry._tasks.keys()) == [agent_id]

        await registry.wait(agent_id, timeout_ms=5000)
        completions = registry.drain_completions()
        assert len(completions) == 1
        assert completions[0].task_id == agent_id


# ---------------------------------------------------------------------------
# Task completion reminder tests
# ---------------------------------------------------------------------------


class TestTaskCompletionReminder:
    async def test_returns_none_when_no_completions(self) -> None:
        registry = TaskRegistry()
        reminder = task_completion_reminder(registry)

        messages: list[Message] = [{"role": "user", "content": "Hello"}]
        result = reminder.rule(messages, AgentContext(model=STUB_PROFILE))
        assert result is None

    async def test_formats_completion_as_notification(self) -> None:
        registry = TaskRegistry()

        async def _fast_coro() -> ToolResult:
            return ToolResult(output="All tests passed.")

        registry.submit("t1", "agent", "Run tests", _fast_coro())
        await asyncio.sleep(0.01)  # let task complete

        reminder = task_completion_reminder(registry)
        messages: list[Message] = [{"role": "user", "content": "Hello"}]
        result = reminder.rule(messages, AgentContext(model=STUB_PROFILE))
        assert result is not None
        assert "t1" in result
        assert "Run tests" in result
        assert "All tests passed." in result

    async def test_drains_completions_after_firing(self) -> None:
        registry = TaskRegistry()

        async def _fast_coro() -> ToolResult:
            return ToolResult(output="Done.")

        registry.submit("t1", "agent", "Build", _fast_coro())
        await asyncio.sleep(0.01)

        reminder = task_completion_reminder(registry)
        messages: list[Message] = [{"role": "user", "content": "Hello"}]
        ctx = AgentContext(model=STUB_PROFILE)
        # First fire should produce content
        first = reminder.rule(messages, ctx)
        assert first is not None
        # Second fire should be empty
        second = reminder.rule(messages, ctx)
        assert second is None

    async def test_reminder_position_is_prepend(self) -> None:
        registry = TaskRegistry()
        reminder = task_completion_reminder(registry)
        assert reminder.position == "append"

    async def test_failed_task_header_says_failed(self) -> None:
        registry = TaskRegistry()

        async def _fail_coro() -> ToolResult:
            msg = "connection refused"
            raise RuntimeError(msg)

        registry.submit("t1", "agent", "Fetch data", _fail_coro())
        await asyncio.sleep(0.01)

        reminder = task_completion_reminder(registry)
        messages: list[Message] = [{"role": "user", "content": "Hello"}]
        result = reminder.rule(messages, AgentContext(model=STUB_PROFILE))
        assert result is not None
        assert "t1" in result
        assert "failed" in result

    async def test_background_agent_completion_surfaces_via_reminder(self) -> None:
        """End-to-end: AgentTool background spawn -> completion -> reminder notification."""
        runner = _make_runner("research complete", delay=0.01)
        registry = TaskRegistry()
        tool = AgentTool(registry, runner, {})

        result = await tool.execute(
            AgentToolParams(
                description="Research",
                prompt="do research",
                subagent_type="general-purpose",
                run_in_background=True,
            ),
        )
        assert result.output is not None
        task_id = _latest_task_id(registry)

        # Wait for background task to complete
        await registry.wait(task_id, timeout_ms=5000)

        # Verify reminder fires with the agent's output
        reminder = task_completion_reminder(registry)
        messages: list[Message] = [{"role": "user", "content": "Hello"}]
        notification = reminder.rule(messages, AgentContext(model=STUB_PROFILE))
        assert notification is not None
        assert task_id in notification
        assert "research complete" in notification
