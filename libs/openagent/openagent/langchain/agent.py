"""LangChain agent factory for OpenAgent.

Creates an OpenAgent agent using LangChain's agent infrastructure.
No CapabilityRegistry — tools are plain lists. System prompt is managed
in state["messages"] by the middleware, not by LangChain's auto-prepend.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Self

from langchain.agents import create_agent as _create_langchain_agent
from langchain.chat_models import init_chat_model

from openagent.harness import BUILTIN_REMINDERS, DEFAULT_SKILL_PATHS, EnvironmentResolver, PermissionGate, SkillResolver, task_completion_reminder
from openagent.harness.model import _FALLBACK_COMPACTION_THRESHOLD, ModelProfile
from openagent.langchain.middleware import AgentMiddleware
from openagent.langchain.subagent import LangChainSubagentRunner
from openagent.prompts import FRESH_SESSION, RESUMED_SESSION, compose
from openagent.tasks import TaskRegistry
from openagent.tools import SkillTool, TodoWriteTool, create_cli_tools, create_web_tools
from openagent.tools.task import TaskOutputTool, TaskStopTool
from openagent.tools.task.agent import AgentTool
from openagent.trace import init_langchain_tracing
from openagent.types import AgentContext, CompletionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping, Sequence
    from types import TracebackType

    from langchain_core.language_models import BaseChatModel
    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.types import Checkpointer

    from openagent.computer import Computer
    from openagent.harness import Reminder
    from openagent.harness.definition import AgentDefinition
    from openagent.mcp import McpClient
    from openagent.tools.base import BaseAgentTool
    from openagent.tools.web import FetchProvider, SearchProvider
    from openagent.types import McpServerConfig, Skill

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 3  # Rough approximation; no tokenizer available yet.
init_langchain_tracing()


class Agent:
    """An OpenAgent agent with managed resources.

    Wraps a compiled LangGraph agent and owns async resources
    (e.g. MCP connections) that must be cleaned up.

    Use as an async context manager or call ``aclose()`` explicitly::

        async with await create_agent(model, computer, ...) as agent:
            print(agent.model_name)  # resolved model name
            print(len(agent.tools))  # all registered tools
            result = await agent.ainvoke({"messages": [...]})

    Attributes:
        model: The model profile.
        model_name: Resolved model name string.
        computer: The Computer instance.
        tools: All registered tools (core + web + extra + MCP + task).
        skills: Discovered skills.
        mcps: Connected MCP clients (name, instructions, tools, status).
        agents: Registered agent definitions.
        system_prompt: The assembled initial system prompt.
        graph: The underlying LangGraph compiled graph.
    """

    def __init__(
        self,
        context: AgentContext,
        graph: CompiledStateGraph[Any],
        resources: AsyncExitStack,
        *,
        system_prompt: str,
        task_registry: TaskRegistry,
        computer: Computer | None = None,
    ) -> None:
        """Initialize the agent with context, graph, and resources."""
        self._context = context
        self._graph = graph
        self._resources = resources
        self._system_prompt = system_prompt
        self._task_registry = task_registry
        self._computer = computer

    @property
    def model(self) -> ModelProfile:
        """The model profile."""
        return self._context.model

    @property
    def model_name(self) -> str:
        """Resolved model name string."""
        return self._context.model_name

    @property
    def computer(self) -> Computer | None:
        """The Computer instance."""
        return self._computer

    @property
    def tools(self) -> list[BaseAgentTool[Any]]:
        """All registered tools (core + web + extra + MCP + task)."""
        return list(self._context.tools)

    @property
    def skills(self) -> list[Skill]:
        """Discovered skills."""
        return list(self._context.skills)

    @property
    def mcps(self) -> list[McpClient]:
        """Connected MCP clients (name, instructions, tools, status)."""
        return list(self._context.mcps)

    @property
    def agents(self) -> dict[str, AgentDefinition]:
        """Registered agent definitions."""
        return dict(self._context.agents)

    @property
    def system_prompt(self) -> str:
        """The assembled initial system prompt."""
        return self._system_prompt

    @property
    def graph(self) -> CompiledStateGraph[Any]:
        """The underlying LangGraph compiled graph."""
        return self._graph

    async def ainvoke(
        self,
        input: dict[str, Any],  # noqa: A002
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Invoke the agent (single response)."""
        return await self._graph.ainvoke(input, config, **kwargs)

    async def astream(
        self,
        input: dict[str, Any],  # noqa: A002
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Stream agent events."""
        async for event in self._graph.astream(input, config, **kwargs):
            yield event

    async def astream_events(
        self,
        input: dict[str, Any],  # noqa: A002
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        """Stream detailed events including subagent internals.

        Uses LangGraph's ``astream_events(version="v2")``. When a subagent
        runs inside a Task tool, its token-level and tool-level events
        propagate through the shared callback infrastructure and appear
        in this stream alongside the parent's own events.
        """
        async for event in self._graph.astream_events(input, config, version="v2", **kwargs):
            yield event

    async def aclose(self) -> None:
        """Release all owned resources (MCP connections, etc.)."""
        await self._task_registry.cancel_all()
        await self._resources.aclose()

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and release resources."""
        await self.aclose()

    def __repr__(self) -> str:
        """Return a string representation of the agent."""
        tool_names = [t.name for t in self._context.tools]
        agent_names = list(self._context.agents.keys())
        skill_names = [s.name for s in self._context.skills]
        mcp_names = [m.name for m in self._context.mcps]
        return f"Agent(model={self.model_name!r}, tools={tool_names!r}, agents={agent_names!r}, skills={skill_names!r}, mcps={mcp_names!r})"


async def create_agent(
    model: str | BaseChatModel | ModelProfile,
    computer: Computer,
    *,
    fast_model: str | BaseChatModel | ModelProfile | None = None,
    mcp_servers: Mapping[str, McpServerConfig] | None = None,
    agents: Mapping[str, AgentDefinition] | None = None,
    search_provider: SearchProvider | None = None,
    fetch_provider: FetchProvider | None = None,
    skill_paths: Sequence[str] = DEFAULT_SKILL_PATHS,
    system_prompt: str | None = None,
    reminders: Sequence[Reminder] = BUILTIN_REMINDERS,
    extra_tools: Sequence[BaseAgentTool[Any]] | None = None,
    checkpointer: Checkpointer | None = None,
) -> Agent:
    """Create an OpenAgent agent using LangChain.

    OpenAgent agents require a LLM that supports tool calling.

    Default tools: ``Bash``, ``Read``, ``Write``, ``Edit``, ``Glob``,
    ``Grep``.  Web tools (``WebSearch``, ``WebFetch``) are included
    only when their providers are supplied.  The ``Skill`` tool is
    included when skills are discovered from configured search paths.
    ``Task`` and ``TaskOutput`` tools are always included.

    Args:
        model: The model to use, e.g. ``"openai:gpt-5.2"``.
            Accepts a LangChain ``init_chat_model`` specifier, a
            pre-configured ``BaseChatModel`` instance, or a
            ``ModelProfile`` for context-window-aware compaction.
        computer: The Computer instance that CLI tools execute against.
        fast_model: Optional model for internal tasks requiring quick
            responses (e.g. web tool summarization). Accepts the same
            input forms as ``model``. Defaults to ``model`` when not
            provided.
        mcp_servers: MCP server configurations keyed by server name.
            The name is used as the tool prefix (``mcp__<name>__<tool>``).
            OpenAgent connects to each server, discovers their tools,
            and manages connections for the agent's lifetime.
        agents: Named agent definitions for subagent spawning via
            the Task tool. Each key becomes a ``subagent_type`` value.
        search_provider: Web search provider.
        fetch_provider: Web fetch provider.
        skill_paths: Directories to scan for skill folders.
            Defaults to ``DEFAULT_SKILL_PATHS``. Pass ``()`` to disable.
        system_prompt: Custom system prompt. When provided, the
            framework will NOT compose its own prompt. The developer is
            responsible for including all necessary instructions.
        reminders: Reminder rules for dynamic system-reminder injection.
            Defaults to ``BUILTIN_REMINDERS``. Pass a custom sequence to
            override completely, or extend with
            ``[*BUILTIN_REMINDERS, my_reminder]``.
        extra_tools: Additional ``BaseAgentTool`` instances beyond the
            built-in set. Merged with default tools and fully visible in
            the system prompt, ``AgentContext``, and compaction rebuild.
        checkpointer: LangGraph checkpointer for conversation persistence.

    Returns:
        A configured OpenAgent agent. Use as an async context manager
        to ensure MCP connections are cleaned up.

    Examples:
        Basic usage::

            async with await create_agent("openai:gpt-5.2", LocalNativeComputer()) as agent:
                result = await agent.ainvoke({"messages": [...]})

        With MCP servers::

            async with await create_agent(
                model,
                computer,
                mcp_servers={
                    "gh": {"type": "http", "url": "https://mcp.github.com/mcp"},
                },
            ) as agent:
                result = await agent.ainvoke({"messages": [...]})
    """
    # 1. Resource stack for managed async resources
    resources = AsyncExitStack()
    await resources.__aenter__()

    try:
        # 2. Resolve models (warns + applies fallback if threshold unknown)
        main_profile = _resolve_to_profile(model)
        fast_profile = _resolve_to_profile(fast_model) if fast_model is not None else main_profile

        # 3. Eagerly resolve AgentDefinition models (fail fast)
        agents_map: dict[str, AgentDefinition] = dict(agents) if agents else {}
        resolved_agent_models: dict[str, ModelProfile] = {}
        for agent_name, defn in agents_map.items():
            if defn.model is not None:
                resolved_agent_models[agent_name] = _resolve_to_profile(defn.model)

        # 4. Create TaskRegistry (needed by BashTool and task tools)
        registry = TaskRegistry()

        # 5. Concurrent I/O: environment detection, skill discovery, MCP connection
        env_resolver = EnvironmentResolver(computer)
        skill_resolver = SkillResolver(computer, list(skill_paths))
        env, skills, mcp_clients = await asyncio.gather(
            env_resolver.resolve(),
            skill_resolver.discover(),
            _connect_mcps(mcp_servers, resources),
        )

        # 6. Assemble base tools (synchronous — everything needed is resolved)
        base_tools: list[BaseAgentTool[Any]] = [
            *create_cli_tools(computer, registry),
            *create_web_tools(
                search_provider=search_provider,
                fetch_provider=fetch_provider,
                completion_model=_create_completion_model(fast_profile) if search_provider or fetch_provider else None,
            ),
            *([SkillTool(catalog=skill_resolver)] if skills else []),
            TodoWriteTool(),
            TaskOutputTool(registry),
            TaskStopTool(registry),
            *(extra_tools or []),
            *(t for c in mcp_clients for t in c.tools),
        ]

        # 7. Validate agent tool references
        _validate_agent_tools(agents_map, base_tools)

        # 8. Create LangChainSubagentRunner
        permission_gate = PermissionGate()
        runner = LangChainSubagentRunner(
            default_model=main_profile,
            base_tools=base_tools,
            definitions=agents_map,
            resolved_models=resolved_agent_models,
            mcps=mcp_clients,
            skills=skills,
            skill_resolver=skill_resolver,
            environment_resolver=env_resolver,
            environment=env,
            permission_gate=permission_gate,
        )

        # 9. Create AgentTool (not a base tool — subagents cannot spawn sub-sub-agents)
        agent_tool = AgentTool(registry, runner, agents_map)

        # 10. Build AgentContext
        all_tools: list[BaseAgentTool[Any]] = [agent_tool, *base_tools]
        ctx = AgentContext(
            model=main_profile,
            tools=all_tools,
            skills=skills,
            mcps=mcp_clients,
            environment=env,
            agents=agents_map,
        )

        # 11. Compose system prompt
        if system_prompt is not None:
            assembled_prompt = system_prompt
            if agents_map:
                logger.warning(
                    "Custom system_prompt provided with agents defined — agent type descriptions will not be auto-injected.",
                )
        else:
            assembled_prompt = compose(FRESH_SESSION, ctx)

        # 12. Assemble reminders (task completion is always present)
        all_reminders = [*reminders, task_completion_reminder(registry)]

        # 13. Create middleware
        prompt_profile = None if system_prompt is not None else RESUMED_SESSION
        middleware = AgentMiddleware(
            context=ctx,
            system_prompt=assembled_prompt,
            permission_gate=permission_gate,
            skill_resolver=skill_resolver,
            environment_resolver=env_resolver,
            reminders=all_reminders,
            prompt_profile=prompt_profile,
        )

        # 14. Create graph
        graph: CompiledStateGraph[Any] = _create_langchain_agent(
            main_profile.model,
            middleware=[middleware],
            checkpointer=checkpointer,
            name="OpenAgent",
        ).with_config({"recursion_limit": 10_000})

        return Agent(
            ctx,
            graph,
            resources,
            system_prompt=assembled_prompt,
            task_registry=registry,
            computer=computer,
        )

    except BaseException:
        await resources.__aexit__(None, None, None)
        raise


async def _connect_mcps(
    mcp_servers: Mapping[str, McpServerConfig] | None,
    resources: AsyncExitStack,
) -> list[McpClient]:
    """Connect to MCP servers and return their clients."""
    if not mcp_servers:
        return []
    from openagent.mcp._connector import McpConnector

    connector = McpConnector(mcp_servers)
    await resources.enter_async_context(connector)
    return connector.clients


def _validate_agent_tools(
    agents_map: dict[str, AgentDefinition],
    base_tools: list[BaseAgentTool[Any]],
) -> None:
    """Validate that all AgentDefinition tool names reference real tools.

    Raises:
        ValueError: If any tool name is unknown or forbidden.
    """
    forbidden = frozenset({AgentTool.name})
    allowed_names = {t.name for t in base_tools}
    for agent_name, defn in agents_map.items():
        for tool_name in defn.tools:
            if tool_name in forbidden:
                msg = f"Agent {agent_name!r}: subagents cannot use {tool_name!r} (sub-sub-agents are disabled)"
                raise ValueError(msg)
            if tool_name not in allowed_names:
                msg = f"Agent {agent_name!r}: unknown tool {tool_name!r}. Available: {sorted(allowed_names)}"
                raise ValueError(msg)


def _resolve_to_profile(
    model: str | BaseChatModel | ModelProfile,
) -> ModelProfile:
    """Resolve any model input to a ModelProfile with guaranteed threshold.

    - ``str`` → ``init_chat_model(str)`` → ``ModelProfile(model=resolved)``
    - ``BaseChatModel`` → ``ModelProfile(model=model)``
    - ``ModelProfile`` → returned as-is

    If ``compaction_threshold`` is still ``None`` after construction
    (neither explicit nor derived from ``context_window``), applies
    ``_FALLBACK_COMPACTION_THRESHOLD`` and logs a warning.
    """
    if isinstance(model, ModelProfile):
        profile = model
    else:
        resolved = init_chat_model(model) if isinstance(model, str) else model
        profile = ModelProfile(model=resolved)

    if profile.context_window is None and profile.compaction_threshold is None:
        # ModelProfile.__post_init__ already logs an advisory warning;
        # here we silently apply the fallback so the agent can proceed.
        profile = replace(profile, compaction_threshold=_FALLBACK_COMPACTION_THRESHOLD)

    return profile


def _create_completion_model(profile: ModelProfile) -> CompletionModel:
    """Bridge a ModelProfile to a framework-agnostic CompletionModel.

    Wraps the profile's BaseChatModel in an async (system, user) → str
    callable and derives max_input_chars from the profile's
    compaction_threshold.
    """

    async def _complete(system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        resp = await profile.model.ainvoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=user),
            ],
            config={"tags": ["openagent:tool"]},
        )
        return str(resp.content)

    assert profile.compaction_threshold is not None  # noqa: S101  # guaranteed by _resolve_to_profile
    return CompletionModel(
        _complete,
        max_input_chars=int(profile.compaction_threshold * _CHARS_PER_TOKEN),
    )
