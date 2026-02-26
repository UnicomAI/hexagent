"""LangChain agent factory for OpenAgent.

Creates an OpenAgent agent using LangChain's agent infrastructure.
No CapabilityRegistry — tools are plain lists. System prompt is managed
in state["messages"] by the middleware, not by LangChain's auto-prepend.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Self

from langchain.agents import create_agent as _create_langchain_agent
from langchain.chat_models import init_chat_model

from openagent.harness import BUILTIN_REMINDERS, DEFAULT_SKILL_PATHS, EnvironmentResolver, PermissionGate, SkillResolver
from openagent.harness.model import _FALLBACK_COMPACTION_THRESHOLD, ModelProfile
from openagent.langchain.middleware import AgentMiddleware
from openagent.prompts import FRESH_SESSION, compose
from openagent.tools import SkillTool, WebFetchTool, WebSearchTool, create_cli_tools
from openagent.types import AgentContext, CompletionModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping, Sequence
    from types import TracebackType

    from langchain_core.language_models import BaseChatModel
    from langchain_core.runnables import RunnableConfig
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer

    from openagent.computer import Computer
    from openagent.harness import Reminder
    from openagent.mcp import McpClient
    from openagent.tools.base import BaseAgentTool
    from openagent.tools.web import FetchProvider, SearchProvider
    from openagent.types import McpServerConfig, Skill

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 3  # Rough approximation; no tokenizer available yet.


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
        model_name: Resolved model name string.
        tools: All registered tools (core + web + extra + MCP).
        skills: Discovered skills.
        mcps: Connected MCP clients (name, instructions, tools, status).
        system_prompt: The assembled initial system prompt.
        graph: The underlying LangGraph compiled graph.
    """

    def __init__(
        self,
        graph: CompiledStateGraph[Any],
        resources: AsyncExitStack,
        *,
        model_name: str,
        tools: list[BaseAgentTool[Any]],
        skills: list[Skill],
        mcps: list[McpClient],
        system_prompt: str,
    ) -> None:
        """Initialize the agent with a graph, resources, and metadata."""
        self._graph = graph
        self._resources = resources
        self._model_name = model_name
        self._tools = tools
        self._skills = skills
        self._mcps = mcps
        self._system_prompt = system_prompt

    @property
    def model_name(self) -> str:
        """Resolved model name string."""
        return self._model_name

    @property
    def tools(self) -> list[BaseAgentTool[Any]]:
        """All registered tools (core + web + extra + MCP)."""
        return list(self._tools)

    @property
    def skills(self) -> list[Skill]:
        """Discovered skills."""
        return list(self._skills)

    @property
    def mcps(self) -> list[McpClient]:
        """Connected MCP clients (name, instructions, tools, status)."""
        return list(self._mcps)

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

    async def aclose(self) -> None:
        """Release all owned resources (MCP connections, etc.)."""
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
        tool_count = len(self._tools)
        skill_count = len(self._skills)
        mcp_count = len(self._mcps)
        return f"Agent(model={self._model_name!r}, tools={tool_count}, skills={skill_count}, mcps={mcp_count})"


async def create_agent(
    model: str | BaseChatModel | ModelProfile,
    computer: Computer,
    *,
    fast_model: str | BaseChatModel | ModelProfile | None = None,
    extra_tools: Sequence[BaseAgentTool[Any]] | None = None,
    mcp_servers: Mapping[str, McpServerConfig] | None = None,
    search_provider: SearchProvider | None = None,
    fetch_provider: FetchProvider | None = None,
    skill_paths: Sequence[str] = DEFAULT_SKILL_PATHS,
    reminders: Sequence[Reminder] = BUILTIN_REMINDERS,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
) -> Agent:
    """Create an OpenAgent agent using LangChain.

    OpenAgent agents require a LLM that supports tool calling.

    Default tools: ``Bash``, ``Read``, ``Write``, ``Edit``, ``Glob``,
    ``Grep``.  Web tools (``WebSearch``, ``WebFetch``) are included
    only when their providers are supplied.  The ``Skill`` tool is
    included when skills are discovered from configured search paths.

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
        extra_tools: Additional ``BaseAgentTool`` instances beyond the
            built-in set. Merged with default tools and fully visible in
            the system prompt, ``AgentContext``, and compaction rebuild.
        mcp_servers: MCP server configurations keyed by server name.
            The name is used as the tool prefix (``mcp__<name>__<tool>``).
            OpenAgent connects to each server, discovers their tools,
            and manages connections for the agent's lifetime.
        search_provider: Web search provider.
        fetch_provider: Web fetch provider.
        skill_paths: Directories to scan for skill folders.
            Defaults to ``DEFAULT_SKILL_PATHS``. Pass ``()`` to disable.
        reminders: Reminder rules for dynamic system-reminder injection.
            Defaults to ``BUILTIN_REMINDERS``. Pass a custom sequence to
            override completely, or extend with
            ``[*BUILTIN_REMINDERS, my_reminder]``.
        checkpointer: LangGraph checkpointer for conversation persistence.
        store: LangGraph store for cross-thread memory.

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

        # 3. Build tools
        tools: list[BaseAgentTool[Any]] = list(create_cli_tools(computer))
        if search_provider is not None:
            tools.append(WebSearchTool(search_provider, model=_create_completion_model(fast_profile)))
        if fetch_provider is not None:
            tools.append(WebFetchTool(fetch_provider, model=_create_completion_model(fast_profile)))
        if extra_tools is not None:
            tools.extend(extra_tools)
        mcp_clients: list[McpClient] = []
        if mcp_servers:
            from openagent.mcp._connector import McpConnector

            connector = McpConnector(mcp_servers)
            await resources.enter_async_context(connector)
            mcp_clients = connector.clients
            tools.extend(connector.tools)

        # 4. Discover skills
        resolver: SkillResolver | None = None
        skills: list[Skill] = []
        if skill_paths:
            resolver = SkillResolver(computer, list(skill_paths))
            skills = await resolver.discover()
            tools.append(SkillTool(catalog=resolver))

        # 5. Detect environment and compose initial system prompt
        model_name = getattr(main_profile.model, "model_name", type(main_profile.model).__name__)
        env_resolver = EnvironmentResolver(computer)
        env = await env_resolver.resolve()
        ctx = AgentContext(model_name=model_name, tools=tools, skills=skills, mcps=mcp_clients, environment=env)
        assembled_prompt = compose(FRESH_SESSION, ctx)

        # 6. Create middleware
        middleware = AgentMiddleware(
            model=main_profile,
            tools=tools,
            system_prompt=assembled_prompt,
            permission_gate=PermissionGate(),
            environment=env,
            environment_resolver=env_resolver,
            skills=skills,
            mcps=mcp_clients,
            skill_resolver=resolver,
            reminders=list(reminders),
        )

        # 7. Create graph
        graph: CompiledStateGraph[Any] = _create_langchain_agent(
            main_profile.model,
            middleware=[middleware],
            checkpointer=checkpointer,
            store=store,
        ).with_config({"recursion_limit": 10_000})

        return Agent(
            graph,
            resources,
            model_name=model_name,
            tools=tools,
            skills=skills,
            mcps=mcp_clients,
            system_prompt=assembled_prompt,
        )

    except BaseException:
        await resources.__aexit__(None, None, None)
        raise


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
        logger.warning(
            "Neither context_window nor compaction_threshold provided for model '%s'. "
            "A fallback threshold of %d tokens will be used to trigger compaction when context grows too long. "
            "[Suggestion: To ensure reliable execution, consider configuring a ModelProfile with context_window and/or compaction_threshold.]",
            getattr(profile.model, "model_name", type(profile.model).__name__),
            _FALLBACK_COMPACTION_THRESHOLD,
        )
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
            ]
        )
        return str(resp.content)

    assert profile.compaction_threshold is not None  # noqa: S101  # guaranteed by _resolve_to_profile
    return CompletionModel(
        _complete,
        max_input_chars=int(profile.compaction_threshold * _CHARS_PER_TOKEN),
    )
