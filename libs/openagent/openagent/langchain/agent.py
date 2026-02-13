"""LangChain agent factory for OpenAgent.

Creates an OpenAgent agent using LangChain's agent infrastructure.
No CapabilityRegistry — tools are plain lists. System prompt is managed
in state["messages"] by the middleware, not by LangChain's auto-prepend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain.agents import create_agent as _create_langchain_agent
from langchain.chat_models import init_chat_model

from openagent.harness import BUILTIN_REMINDERS, DEFAULT_SKILL_PATHS, PermissionGate, SkillResolver
from openagent.harness.model import _FALLBACK_COMPACTION_THRESHOLD, ModelProfile
from openagent.langchain.middleware import AgentMiddleware
from openagent.prompts import FRESH_SESSION, compose
from openagent.tools import SkillTool, WebFetchTool, WebSearchTool, create_cli_tools
from openagent.types import AgentContext, CompletionModel

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.language_models import BaseChatModel
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer

    from openagent.computer import Computer
    from openagent.harness import Reminder
    from openagent.tools.base import BaseAgentTool
    from openagent.tools.web import FetchProvider, SearchProvider
    from openagent.types import Skill

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 3  # Rough approximation; no tokenizer available yet.


async def create_agent(
    model: str | BaseChatModel | ModelProfile,
    computer: Computer,
    *,
    fast_model: str | BaseChatModel | ModelProfile | None = None,
    extra_tools: Sequence[BaseAgentTool[Any]] | None = None,
    search_provider: SearchProvider | None = None,
    fetch_provider: FetchProvider | None = None,
    skill_paths: Sequence[str] = DEFAULT_SKILL_PATHS,
    reminders: Sequence[Reminder] = BUILTIN_REMINDERS,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
) -> CompiledStateGraph[Any]:
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
        A configured OpenAgent agent.

    Examples:
        Basic usage::

            agent = await create_agent("openai:gpt-5.2", LocalNativeComputer())
            result = await agent.ainvoke({"messages": [...]})

        With model-aware compaction::

            from langchain.chat_models import init_chat_model

            profile = ModelProfile(
                model=init_chat_model("openai:gpt-5.2"),
                context_window=128_000,
            )
            agent = await create_agent(profile, computer)

        With a fast model for web tool summarization::

            agent = await create_agent(
                model,
                computer,
                fast_model="openai:gpt-4.1-mini",
                search_provider=my_search,
            )

        With skills::

            agent = await create_agent(model, computer, skill_paths=("/mnt/skills",))
    """
    # 1. Resolve models
    main_profile = _resolve_to_profile(model)
    fast_profile = _resolve_to_profile(fast_model) if fast_model is not None else main_profile

    # 2. Warn at construction time if context_window unknown
    if main_profile.context_window is None:
        logger.warning(
            "No context_window specified. Using fallback compaction threshold (%d). Pass a ModelProfile to create_agent for model-aware compaction.",
            _FALLBACK_COMPACTION_THRESHOLD,
        )

    # 3. Build completion model from fast_profile (for web tools)
    completion_model: CompletionModel | None = None
    if search_provider is not None or fetch_provider is not None:
        completion_model = _create_completion_model(fast_profile)

    # 4. Build tools
    tools: list[BaseAgentTool[Any]] = list(create_cli_tools(computer))
    if search_provider is not None:
        tools.append(WebSearchTool(search_provider, model=completion_model))
    if fetch_provider is not None:
        tools.append(WebFetchTool(fetch_provider, model=completion_model))
    if extra_tools is not None:
        tools.extend(extra_tools)

    # 5. Discover skills
    resolver: SkillResolver | None = None
    skills: list[Skill] = []
    if skill_paths:
        resolver = SkillResolver(computer, list(skill_paths))
        skills = await resolver.discover()
        tools.append(SkillTool(catalog=resolver))

    # 6. Compose initial system prompt
    ctx = AgentContext(tools=tools, skills=skills, mcps=[])
    assembled_prompt = compose(FRESH_SESSION, ctx)

    # 7. Create middleware
    middleware = AgentMiddleware(
        model=main_profile,
        tools=tools,
        system_prompt=assembled_prompt,
        permission_gate=PermissionGate(),
        skills=skills,
        skill_resolver=resolver,
        reminders=list(reminders),
    )

    # 8. Create agent
    # NOTE: system_prompt=None — we manage the SystemMessage in state["messages"]
    # via the middleware's first-turn injection and compaction rebuild.
    # All tools are provided by the middleware (via its .tools property).
    return _create_langchain_agent(
        main_profile.model,
        middleware=[middleware],
        checkpointer=checkpointer,
        store=store,
    ).with_config({"recursion_limit": 10_000})


def _resolve_to_profile(
    model: str | BaseChatModel | ModelProfile,
) -> ModelProfile:
    """Resolve any model input to a ModelProfile.

    - ``str`` → ``init_chat_model(str)`` → ``ModelProfile(model=resolved)``
    - ``BaseChatModel`` → ``ModelProfile(model=model)``
    - ``ModelProfile`` → returned as-is
    """
    if isinstance(model, ModelProfile):
        return model
    resolved = init_chat_model(model) if isinstance(model, str) else model
    return ModelProfile(model=resolved)


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

    assert profile.compaction_threshold is not None  # noqa: S101  # always set by __post_init__
    return CompletionModel(
        _complete,
        max_input_chars=int(profile.compaction_threshold * _CHARS_PER_TOKEN),
    )
