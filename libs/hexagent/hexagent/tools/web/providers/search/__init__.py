"""Search providers for WebSearchTool.

Available providers:
- BochaSearchProvider: AI-optimized search, requires API key
- TavilySearchProvider: AI-optimized search, requires API key
- BraveSearchProvider: Privacy-focused search, requires API key
"""

from __future__ import annotations

from hexagent.tools.web.providers.search.base import (
    SearchProvider,
    SearchResult,
    SearchResultItem,
)
from hexagent.tools.web.providers.search.bocha import BochaSearchProvider
from hexagent.tools.web.providers.search.brave import BraveSearchProvider
from hexagent.tools.web.providers.search.tavily import TavilySearchProvider

__all__ = [
    "BochaSearchProvider",
    "BraveSearchProvider",
    "SearchProvider",
    "SearchResult",
    "SearchResultItem",
    "TavilySearchProvider",
]
