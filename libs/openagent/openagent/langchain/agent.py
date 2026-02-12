"""LangChain agent factory for OpenAgent.

Creates an OpenAgent agent using LangChain's agent infrastructure.
No CapabilityRegistry — tools are plain lists. System prompt is managed
in state["messages"] by the middleware, not by LangChain's auto-prepend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents import create_agent as _create_langchain_agent
from langchain.chat_models import init_chat_model

from openagent.harness import BUILTIN_REMINDERS, DEFAULT_SKILL_PATHS, PermissionGate, SkillResolver
from openagent.harness.model import _FALLBACK_COMPACTION_THRESHOLD, ModelProfile
from openagent.langchain.middleware import AgentMiddleware
from openagent.prompts import FRESH_SESSION, RESUMED_SESSION, compose, load, substitute
from openagent.tools import SkillTool, WebFetchTool, WebSearchTool, create_cli_tools
from openagent.types import AgentContext

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import BaseMessage
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer

    from openagent.computer import Computer
    from openagent.harness import Reminder
    from openagent.tools.base import BaseAgentTool
    from openagent.tools.web import FetchProvider, SearchProvider
    from openagent.types import Skill


async def create_agent(
    model: str | BaseChatModel | ModelProfile,
    computer: Computer,
    *,
    skill_paths: Sequence[str] = DEFAULT_SKILL_PATHS,
    search_provider: SearchProvider | None = None,
    fetch_provider: FetchProvider | None = None,
    extra_tools: Sequence[BaseAgentTool[Any]] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    reminders: Sequence[Reminder] = BUILTIN_REMINDERS,
) -> CompiledStateGraph[Any]:
    """Create an OpenAgent agent using LangChain.

    OpenAgent agents require a LLM that supports tool calling.

    Default tools: ``bash``, ``read``, ``write``, ``edit``, ``glob``,
    ``grep``.  Web tools (``web_search``, ``web_fetch``) are included
    only when their providers are supplied.  The ``skill`` tool is
    included when skills are discovered from configured search paths.

    Args:
        model: The model to use, e.g. ``"openai:gpt-5.2"``.
            Accepts a LangChain ``init_chat_model`` specifier, a
            pre-configured ``BaseChatModel`` instance, or a
            ``ModelProfile`` for context-window-aware compaction.
        computer: The Computer instance that CLI tools execute against.
        skill_paths: Directories to scan for skill folders.
            Defaults to ``DEFAULT_SKILL_PATHS``. Pass ``()`` to disable.
        search_provider: Web search provider.
        fetch_provider: Web fetch provider.
        extra_tools: Additional ``BaseAgentTool`` instances beyond the
            built-in set. Merged with default tools and fully visible in
            the system prompt, ``AgentContext``, and compaction rebuild.
        checkpointer: LangGraph checkpointer for conversation persistence.
        store: LangGraph store for cross-thread memory.
        reminders: Reminder rules for dynamic system-reminder injection.
            Defaults to ``BUILTIN_REMINDERS``. Pass a custom sequence to
            override completely, or extend with
            ``[*BUILTIN_REMINDERS, my_reminder]``.

    Returns:
        A configured OpenAgent agent.

    Examples:
        Basic usage::

            agent = await create_agent("openai:gpt-5.2", LocalNativeComputer())
            result = await agent.ainvoke({"messages": [...]})

        With model-aware compaction::

            profile = ModelProfile(model="openai:gpt-5.2", context_window=128_000)
            agent = await create_agent(profile, computer)

        With skills::

            agent = await create_agent(model, computer, skill_paths=("/mnt/skills",))
    """
    # Initialize model
    resolved_model, compaction_threshold, using_default_threshold = _resolve_model_config(model)

    # Build tools
    tools: list[BaseAgentTool[Any]] = list(create_cli_tools(computer))
    if search_provider is not None:
        tools.append(WebSearchTool(search_provider))
    if fetch_provider is not None:
        tools.append(WebFetchTool(fetch_provider))
    if extra_tools is not None:
        tools.extend(extra_tools)

    # Discover skills
    resolver: SkillResolver | None = None
    skills: list[Skill] = []
    if skill_paths:
        resolver = SkillResolver(computer, list(skill_paths))
        skills = await resolver.discover()
        tools.append(SkillTool(catalog=resolver))

    # Assemble initial system prompt
    ctx = AgentContext(
        tools=tools,
        skills=skills,
        mcps=[],
    )
    assembled_prompt = compose(FRESH_SESSION, ctx)

    # Create rebuild callback for compaction
    rebuild = _make_rebuild_callback(
        resolver=resolver,
        tools=tools,
        summary_template=load("user_prompt_compaction_summary_rebuild"),
    )

    # Create middleware (THE runtime)
    middleware = AgentMiddleware(
        tools=tools,
        system_prompt=assembled_prompt,
        skills=skills,
        permission_gate=PermissionGate(),
        compaction_prompt=load("user_prompt_compaction_request"),
        compaction_threshold=compaction_threshold,
        using_default_threshold=using_default_threshold,
        skill_resolver=resolver,
        reminders=list(reminders),
        rebuild_callback=rebuild,
    )

    # NOTE: system_prompt=None — we manage the SystemMessage in state["messages"]
    # via the middleware's first-turn injection and compaction rebuild.
    # All tools are provided by the middleware (via its .tools property).
    return _create_langchain_agent(
        resolved_model,
        middleware=[middleware],
        checkpointer=checkpointer,
        store=store,
    ).with_config({"recursion_limit": 1000})


def _resolve_model_config(
    model: str | BaseChatModel | ModelProfile,
) -> tuple[BaseChatModel, int, bool]:
    """Resolve model argument to (model, compaction_threshold, using_default).

    Returns:
        A tuple of (resolved BaseChatModel, compaction threshold,
        using_default_threshold).
    """
    if isinstance(model, ModelProfile):
        resolved = init_chat_model(model.model) if isinstance(model.model, str) else model.model
        assert model.compaction_threshold is not None  # noqa: S101
        return resolved, model.compaction_threshold, False

    resolved = init_chat_model(model) if isinstance(model, str) else model
    return resolved, _FALLBACK_COMPACTION_THRESHOLD, True


def _make_rebuild_callback(
    *,
    resolver: SkillResolver | None,
    tools: Sequence[BaseAgentTool[Any]],
    summary_template: str,
) -> Callable[[str], Awaitable[list[BaseMessage]]]:
    """Create a callback that rebuilds messages after compaction.

    At compaction time, this callback:
    1. Re-discovers skills from filesystem (live snapshot, not stale cache)
    2. Composes a fresh system prompt using RESUMED_SESSION profile
    3. Returns [SystemMessage(new_prompt), HumanMessage(summary)]
    """

    async def rebuild(summary: str) -> list[BaseMessage]:
        # Import here to avoid circular import at module level
        from langchain_core.messages import HumanMessage, SystemMessage

        # Re-discover skills for live snapshot
        current_skills: list[Skill] = []
        if resolver is not None:
            current_skills = await resolver.discover()

        # Compose fresh system prompt with current capabilities
        ctx = AgentContext(
            tools=list(tools),
            skills=current_skills,
            mcps=[],
        )
        new_system_prompt = compose(RESUMED_SESSION, ctx)

        # Format summary into the rebuild template
        summary_content = substitute(summary_template, SUMMARY_CONTENT=summary)

        return [
            SystemMessage(content=new_system_prompt),
            HumanMessage(content=summary_content),
        ]

    return rebuild
