"""Web tools for searching and fetching content from the internet.

Tools:
- WebSearchTool: Search the web for information
- WebFetchTool: Fetch and extract content from web pages

Providers:
- TavilySearchProvider, BraveSearchProvider: Search backends
- JinaFetchProvider, FirecrawlFetchProvider: Fetch backends

Example:
    >>> from openagent.tools.web import WebSearchTool, TavilySearchProvider
    >>> tool = WebSearchTool(TavilySearchProvider())
"""

from __future__ import annotations

from openagent.tools.web._cache import clear_caches
from openagent.tools.web.fetch import WebFetchTool
from openagent.tools.web.providers import (
    BraveSearchProvider,
    FetchProvider,
    FirecrawlFetchProvider,
    JinaFetchProvider,
    SearchProvider,
    TavilySearchProvider,
)
from openagent.tools.web.search import WebSearchTool

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
]
