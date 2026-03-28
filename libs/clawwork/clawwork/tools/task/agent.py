"""AgentTool — agent-facing tool for spawning subagents.

The :class:`~clawwork.types.SubagentRunner` protocol and
:class:`~clawwork.types.SubagentResult` data type live in
:mod:`clawwork.types`.
"""

from __future__ import annotations

import logging
import secrets
from typing import TYPE_CHECKING, Any

from clawwork.tools.base import BaseAgentTool
from clawwork.types import AgentToolParams, SubagentRunner, ToolResult

if TYPE_CHECKING:
    from collections.abc import Mapping

    from clawwork.harness.definition import AgentDefinition
    from clawwork.tasks import TaskRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AgentTool
# ---------------------------------------------------------------------------


class AgentTool(BaseAgentTool[AgentToolParams]):
    """Delegate work to a subagent."""

    name: str = "Agent"
    description: str = "Launch a subagent to handle a task."
    args_schema = AgentToolParams

    def __init__(
        self,
        registry: TaskRegistry,
        runner: SubagentRunner,
        agents: Mapping[str, AgentDefinition],
    ) -> None:
        """Initialize with a task registry, runner, and agent definitions."""
        self._registry = registry
        self._runner = runner
        self._agents = agents
        self._conversations: dict[str, list[Any]] = {}

    async def execute(self, params: AgentToolParams) -> ToolResult:
        """Execute the Agent tool."""
        if params.subagent_type != "general-purpose" and params.subagent_type not in self._agents:
            available = ", ".join(["general-purpose", *self._agents.keys()])
            return ToolResult(
                error=f"Unknown subagent type: {params.subagent_type!r}. Available: {available}",
            )

        # Determine agent_id — stable identity
        if params.resume is not None:
            agent_id = params.resume
            if agent_id not in self._conversations:
                return ToolResult(error=f"Cannot resume: agent {agent_id!r} not found")
            prior_messages: list[Any] = self._conversations[agent_id]
        else:
            agent_id = secrets.token_hex(8)
            prior_messages = []

        # Register in registry (handles "still running" guard)
        try:
            if params.run_in_background:
                self._registry.submit(
                    agent_id,
                    "agent",
                    params.description,
                    self._run_agent(agent_id, params, prior_messages),
                )
                return ToolResult(
                    output=f"Agent running in background with ID: {agent_id}",
                )
            self._registry.register(agent_id, "agent", params.description)
        except RuntimeError:
            return ToolResult(
                error=f"Cannot resume agent {agent_id!r}: it is still running. Use TaskStop to cancel it first, or wait for it to complete.",
            )

        # Foreground — run synchronously, then deposit result in registry
        try:
            result = await self._run_and_save(agent_id, params, prior_messages)
        except Exception as exc:  # noqa: BLE001
            error_result = ToolResult(error=str(exc))
            self._registry.complete(agent_id, error_result, status="failed")
            return error_result
        else:
            self._registry.complete(agent_id, result)
            return result

    async def _run_agent(
        self,
        agent_id: str,
        params: AgentToolParams,
        prior_messages: list[Any],
    ) -> ToolResult:
        """Background coroutine submitted to registry."""
        return await self._run_and_save(agent_id, params, prior_messages)

    async def _run_and_save(
        self,
        task_id: str,
        params: AgentToolParams,
        prior_messages: list[Any],
    ) -> ToolResult:
        """Execute subagent, save conversation state, return ToolResult.

        Does NOT catch exceptions — callers handle errors differently:
        - Foreground: execute() catches -> ToolResult(error=...)
        - Background: registry._run() catches -> status='failed'
        """
        definition = self._runner.get_definition(params.subagent_type)
        spawn_result = await self._runner.run(
            definition,
            params.prompt,
            prior_messages or None,
            task_id=task_id,
        )
        self._conversations[task_id] = spawn_result.messages
        return ToolResult(
            output=spawn_result.output or "",
            system=f"Agent ID: {task_id} (for resuming to continue this agent's work if needed)",
        )
