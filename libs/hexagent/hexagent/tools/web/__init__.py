"""Web tools for searching and fetching content from the internet.

Tools:
- WebSearchTool: Search the web for information
- WebFetchTool: Fetch and extract content from web pages

Providers:
- TavilySearchProvider, BraveSearchProvider: Search backends
- JinaFetchProvider, FirecrawlFetchProvider: Fetch backends

Factory functions:
- create_web_tools: Create web tools when providers are supplied

Example:
    >>> from hexagent.tools.web import WebSearchTool, TavilySearchProvider
    >>> tool = WebSearchTool(TavilySearchProvider())
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from hexagent.tools.web._cache import clear_caches
from hexagent.tools.web.fetch import WebFetchTool
from hexagent.tools.web.providers import (
    BraveSearchProvider,
    FetchProvider,
    FirecrawlFetchProvider,
    JinaFetchProvider,
    SearchProvider,
    TavilySearchProvider,
)
from hexagent.tools.web.search import WebSearchTool

if TYPE_CHECKING:
    from hexagent.tools.base import BaseAgentTool
    from hexagent.types import CompletionModel


def create_web_tools(
    *,
    search_provider: SearchProvider | None = None,
    fetch_provider: FetchProvider | None = None,
    completion_model: CompletionModel | None = None,
) -> list[BaseAgentTool[Any]]:
    """Create web tools for the supplied providers.

    Returns an empty list when no providers are given.

    Args:
        search_provider: Web search backend.
        fetch_provider: Web fetch backend.
        completion_model: Optional LLM for summarization in search/fetch results.

    Returns:
        List of web tool instances (WebSearchTool and/or WebFetchTool).
    """
    tools: list[BaseAgentTool[Any]] = []
    if search_provider is not None:
        tools.append(WebSearchTool(search_provider, model=completion_model))
    if fetch_provider is not None:
        tools.append(WebFetchTool(fetch_provider, model=completion_model))
    return tools


__all__ = [
    "BraveSearchProvider",
    "FetchProvider",
    "FirecrawlFetchProvider",
    "JinaFetchProvider",
    "SearchProvider",
    "TavilySearchProvider",
    "WebFetchTool",
    "WebSearchTool",
    "clear_caches",
    "create_web_tools",
]
