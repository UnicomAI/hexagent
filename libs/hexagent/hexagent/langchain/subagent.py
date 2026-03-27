"""LangChain-specific subagent runner.

Provides the concrete LangChain-based runner that satisfies the
:class:`~hexagent.types.SubagentRunner` protocol.

Main components:

- :class:`LangChainSubagentRunner` — executes a subagent with its own
  context and tools using LangChain's agent infrastructure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from hexagent.prompts import SUBAGENT_SESSION, compose
from hexagent.types import AgentContext, SubagentResult

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hexagent.harness.definition import AgentDefinition
    from hexagent.harness.environment import EnvironmentResolver
    from hexagent.harness.model import ModelProfile
    from hexagent.harness.permission import PermissionGate
    from hexagent.harness.reminders import Reminder
    from hexagent.harness.skills import SkillResolver
    from hexagent.mcp import McpClient
    from hexagent.tools.base import BaseAgentTool
    from hexagent.types import ApprovalCallback, EnvironmentContext, Skill

logger = logging.getLogger(__name__)

SUBAGENT_EVENT_TAG_PREFIX = "hexagent:subagent:"
"""Prefix for tags added to subagent events.

Each subagent invocation is tagged ``"hexagent:subagent:<task_id>"``.
Consumers can check for the prefix to detect *any* subagent event,
or match the full tag to identify a specific task.  Works for both
foreground and background tasks.
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _extract_final_output(messages: list[Any]) -> str:
    """Extract text from the last AIMessage in a conversation."""
    from langchain_core.messages import AIMessage

    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(block.get("text", "") if isinstance(block, dict) else str(block) for block in content)
    return ""


# ---------------------------------------------------------------------------
# LangChainSubagentRunner
# ---------------------------------------------------------------------------


class LangChainSubagentRunner:
    """Executes subagents with isolated context and tools.

    Takes all dependencies explicitly — no config objects, no closures.
    Each call to :meth:`run` creates a fresh ``AgentContext``, composes
    a system prompt, and invokes a new LangChain agent graph.
    """

    def __init__(
        self,
        *,
        default_model: ModelProfile,
        base_tools: Sequence[BaseAgentTool[Any]],
        definitions: Mapping[str, AgentDefinition],
        resolved_models: Mapping[str, ModelProfile],
        mcps: Sequence[McpClient],
        skills: Sequence[Skill],
        skill_resolver: SkillResolver | None,
        environment_resolver: EnvironmentResolver,
        environment: EnvironmentContext,
        permission_gate: PermissionGate,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        """Initialize the runner with all dependencies.

        Args:
            default_model: Fallback model for general-purpose subagents.
            base_tools: Tools EXCLUDING Agent/TaskOutput/TaskStop.
            definitions: Agent type registry.
            resolved_models: Eagerly resolved per-agent ModelProfiles.
            mcps: MCP clients shared from parent.
            skills: Discovered skills.
            skill_resolver: For skill discovery/loading. None disables skills.
            environment_resolver: Resolves runtime environment.
            environment: Current environment snapshot.
            permission_gate: Permission checking.
            approval_callback: Human-in-the-loop callback.
        """
        self._default_model = default_model
        self._base_tools = list(base_tools)
        self._definitions = dict(definitions)
        self._resolved_models = dict(resolved_models)
        self._mcps = list(mcps)
        self._skills = list(skills)
        self._skill_resolver = skill_resolver
        self._environment_resolver = environment_resolver
        self._environment = environment
        self._permission_gate = permission_gate
        self._approval_callback = approval_callback

    def get_definition(self, subagent_type: str) -> AgentDefinition | None:
        """Look up an agent definition by type name."""
        return self._definitions.get(subagent_type)

    async def run(
        self,
        definition: AgentDefinition | None,
        prompt: str,
        prior_messages: list[Any] | None = None,
        *,
        task_id: str = "",
    ) -> SubagentResult:
        """Execute a subagent and return its result.

        Args:
            definition: Agent type spec, or None for general-purpose.
            prompt: The task prompt for the subagent.
            prior_messages: Conversation history for resume.
            task_id: Unique task identifier, embedded in event tags so
                consumers can distinguish concurrent subagents.

        Returns:
            SubagentResult with output text and full message history.
        """
        # Deferred imports to avoid circular deps
        from langchain.agents import create_agent as _create_langchain_agent
        from langchain_core.messages import HumanMessage

        from hexagent.langchain.middleware import AgentMiddleware

        # 1. Select model
        type_key: str | None = None
        if definition is not None:
            for key, defn in self._definitions.items():
                if defn is definition:
                    type_key = key
                    break
        sub_profile = self._resolved_models.get(type_key or "") if type_key else None
        if sub_profile is None:
            sub_profile = self._default_model

        # 2. Filter tools
        if definition is not None and definition.tools:
            tool_names = set(definition.tools)
            sub_tools: list[BaseAgentTool[Any]] = [t for t in self._base_tools if t.name in tool_names]
        else:
            sub_tools = list(self._base_tools)

        # 3. Determine skills
        has_skill_tool = any(t.name in ("skill", "Skill") for t in sub_tools)
        sub_skills: list[Skill] = list(self._skills) if has_skill_tool else []
        sub_skill_resolver = self._skill_resolver if has_skill_tool else None
        sub_reminders: list[Reminder] = []
        if has_skill_tool:
            from hexagent.harness.reminders import Reminder as ReminderCls
            from hexagent.harness.reminders import available_skills_reminder

            sub_reminders = [ReminderCls(rule=available_skills_reminder, position="prepend")]

        # 4. Build AgentContext
        sub_ctx = AgentContext(
            model=sub_profile,
            tools=sub_tools,
            skills=sub_skills,
            mcps=list(self._mcps),
            environment=self._environment,
            agents={},
        )

        # 5. Compose prompt
        framework_prompt = compose(SUBAGENT_SESSION, sub_ctx)
        custom = definition.system_prompt if definition is not None else ""
        full_prompt = f"{custom}\n\n{framework_prompt}" if custom else framework_prompt

        # 6. Build middleware
        middleware = AgentMiddleware(
            context=sub_ctx,
            system_prompt=full_prompt,
            permission_gate=self._permission_gate,
            approval_callback=self._approval_callback,
            environment_resolver=self._environment_resolver,
            skill_resolver=sub_skill_resolver,
            reminders=sub_reminders,
            prompt_profile=SUBAGENT_SESSION,
            custom_prompt=custom,
        )

        # 7. Create graph + run
        graph = _create_langchain_agent(sub_profile.model, middleware=[middleware], name="HexAgent Subagent")
        graph = graph.with_config({"recursion_limit": 10_000})

        input_messages = [*prior_messages, HumanMessage(content=prompt)] if prior_messages else [HumanMessage(content=prompt)]

        # Use astream_events so that subagent token/tool events propagate
        # to the parent's astream_events() stream via shared callbacks.
        from langchain_core.runnables.config import ensure_config

        parent_config = ensure_config()
        parent_config["tags"] = [*parent_config.get("tags", []), f"{SUBAGENT_EVENT_TAG_PREFIX}{task_id}"]
        output_messages: list[Any] = []
        root_run_id: str | None = None

        async for event in graph.astream_events(
            {"messages": input_messages},
            config=parent_config,
            version="v2",
        ):
            # The first event is always the subagent graph's own on_chain_start.
            # Capture its run_id so we can match the corresponding on_chain_end
            # (parent_ids is NOT reliable here — it includes the parent's run_ids
            # when nested inside astream_events via ensure_config).
            if root_run_id is None:
                root_run_id = event.get("run_id")

            if event["event"] == "on_chain_end" and event.get("run_id") == root_run_id:
                event_data: dict[str, Any] = dict(event.get("data", {}))
                graph_output = event_data.get("output")
                if isinstance(graph_output, dict) and "messages" in graph_output:
                    output_messages = graph_output["messages"]

        return SubagentResult(
            output=_extract_final_output(output_messages),
            messages=output_messages,
        )
