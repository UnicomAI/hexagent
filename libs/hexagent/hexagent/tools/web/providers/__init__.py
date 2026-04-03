"""Web tool providers.

Fetch providers:
- JinaFetchProvider: Free, no API key required
- FirecrawlFetchProvider: Advanced JS rendering, requires API key
- UnicrawlFetchProvider: Unicrawl API (Firecrawl-compatible), requires API key

Search providers:
- BochaSearchProvider: AI-optimized search, requires API key
- TavilySearchProvider: AI-optimized search, requires API key
- BraveSearchProvider: Privacy-focused search, requires API key
"""

from __future__ import annotations

from hexagent.tools.web.providers.fetch import (
    FetchProvider,
    FetchResult,
    FirecrawlFetchProvider,
    JinaFetchProvider,
    UnicrawlFetchProvider,
)
from hexagent.tools.web.providers.search import (
    BochaSearchProvider,
    BraveSearchProvider,
    SearchProvider,
    SearchResultItem,
    TavilySearchProvider,
)

__all__ = [
    "BochaSearchProvider",
    "BraveSearchProvider",
    "FetchProvider",
    "FetchResult",
    "FirecrawlFetchProvider",
    "JinaFetchProvider",
    "SearchProvider",
    "SearchResultItem",
    "TavilySearchProvider",
    "UnicrawlFetchProvider",
]
