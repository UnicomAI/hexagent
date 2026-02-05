"""LangChain agent factory for OpenAgent.

This module provides the create_agent function that creates an OpenAgent
agent using LangChain's agent infrastructure with runtime modules.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain.agents import create_agent as _create_langchain_agent
from langchain.chat_models import init_chat_model

from openagent.langchain.middleware import AgentMiddleware
from openagent.prompts import PromptLibrary, SystemPromptAssembler
from openagent.runtime import CapabilityRegistry, PermissionGate
from openagent.tools import WebFetchTool, WebSearchTool, create_cli_tools

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer

    from openagent.computer import Computer
    from openagent.tools.web import FetchProvider, SearchProvider

DEFAULT_MODEL = "openai:gpt-5.2"


def create_agent(
    computer: Computer,
    *,
    model: str | BaseChatModel | None = None,
    search_provider: SearchProvider | None = None,
    fetch_provider: FetchProvider | None = None,
    tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    system_prompt: str | None = None,
) -> CompiledStateGraph:
    """Create an OpenAgent agent using LangChain.

    OpenAgent agents require a LLM that supports tool calling.

    Default tools: ``bash``, ``read``, ``write``, ``edit``, ``glob``,
    ``grep``.  Web tools (``web_search``, ``web_fetch``) are included
    only when their providers are supplied.

    Args:
        computer: The Computer instance for CLI tools.
        model: The model to use. Defaults to ``openai:gpt-5``.
        tools: Additional tools the agent should have access to.
        search_provider: Web search provider (e.g. ``TavilySearchProvider()``).
        fetch_provider: Web fetch provider (e.g. ``JinaFetchProvider()``).
        checkpointer: LangGraph checkpointer for conversation persistence.
        store: LangGraph store for cross-thread memory.
        system_prompt: Additional instructions for the agent.

    Returns:
        A configured OpenAgent agent.

    Examples:
        Basic usage with defaults::

            agent = create_agent(LocalNativeComputer())
            result = await agent.ainvoke({"messages": [...]})

        With web tools::

            from openagent.tools.web import TavilySearchProvider, JinaFetchProvider

            agent = create_agent(
                LocalNativeComputer(),
                search_provider=TavilySearchProvider(),
                fetch_provider=JinaFetchProvider(),
            )
    """
    # Initialize model
    if model is None:
        model = init_chat_model(DEFAULT_MODEL)
    elif isinstance(model, str):
        model = init_chat_model(model)

    # Initialize prompt system
    library = PromptLibrary()

    # Build registry with all default tools
    registry = _create_default_registry(
        computer,
        search_provider=search_provider,
        fetch_provider=fetch_provider,
    )

    # Assemble system prompt
    assembler = SystemPromptAssembler()
    assembled_prompt = assembler.assemble(
        library=library,
        tools=registry.get_tools(),
        skills=registry.get_skills(),
        mcps=registry.get_mcps(),
        user_instructions=system_prompt,
    )

    # Create middleware
    middleware = AgentMiddleware(
        registry=registry,
        system_prompt=assembled_prompt,
        permission_gate=PermissionGate(),
        compaction_prompt=library.get("compaction/request"),
        summary_rebuild_template=library.get("compaction/summary_rebuild"),
    )

    return _create_langchain_agent(
        model,
        tools=tools,
        middleware=[middleware],
        checkpointer=checkpointer,
        store=store,
    ).with_config({"recursion_limit": 1000})


def _create_default_registry(
    computer: Computer,
    *,
    search_provider: SearchProvider | None = None,
    fetch_provider: FetchProvider | None = None,
) -> CapabilityRegistry:
    """Create a registry populated with all default tools.

    Args:
        computer: The Computer instance for CLI tools.
        search_provider: Optional web search provider.
        fetch_provider: Optional web fetch provider.

    Returns:
        A CapabilityRegistry with all default tools registered.
    """
    registry = CapabilityRegistry()

    for tool in create_cli_tools(computer):
        registry.register_tool(tool)

    if search_provider is not None:
        registry.register_tool(WebSearchTool(search_provider))

    if fetch_provider is not None:
        registry.register_tool(WebFetchTool(fetch_provider))

    return registry
