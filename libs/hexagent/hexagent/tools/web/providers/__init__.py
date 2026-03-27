"""Web tool providers.

Fetch providers:
- JinaFetchProvider: Free, no API key required
- FirecrawlFetchProvider: Advanced JS rendering, requires API key

Search providers:
- TavilySearchProvider: AI-optimized search, requires API key
- BraveSearchProvider: Privacy-focused search, requires API key
"""

from __future__ import annotations

from hexagent.tools.web.providers.fetch import (
    FetchProvider,
    FetchResult,
    FirecrawlFetchProvider,
    JinaFetchProvider,
)
from hexagent.tools.web.providers.search import (
    BraveSearchProvider,
    SearchProvider,
    SearchResultItem,
    TavilySearchProvider,
)

__all__ = [
    "BraveSearchProvider",
    "FetchProvider",
    "FetchResult",
    "FirecrawlFetchProvider",
    "JinaFetchProvider",
    "SearchProvider",
    "SearchResultItem",
    "TavilySearchProvider",
]
