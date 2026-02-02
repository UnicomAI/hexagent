"""Search providers for WebSearchTool.

Available providers:
- TavilySearchProvider: AI-optimized search, requires API key
- BraveSearchProvider: Privacy-focused search, requires API key
"""

from __future__ import annotations

from openagent.tools.web.providers.search.base import (
    SearchProvider,
    SearchResult,
    SearchResultItem,
)
from openagent.tools.web.providers.search.brave import BraveSearchProvider
from openagent.tools.web.providers.search.tavily import TavilySearchProvider

__all__ = [
    "BraveSearchProvider",
    "SearchProvider",
    "SearchResult",
    "SearchResultItem",
    "TavilySearchProvider",
]
