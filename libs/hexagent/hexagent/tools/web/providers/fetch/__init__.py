"""Fetch providers for WebFetchTool.

Available providers:
- JinaFetchProvider: Free, no API key required
- FirecrawlFetchProvider: Advanced JS rendering, requires API key
"""

from __future__ import annotations

from hexagent.tools.web.providers.fetch.base import FetchProvider, FetchResult
from hexagent.tools.web.providers.fetch.firecrawl import FirecrawlFetchProvider
from hexagent.tools.web.providers.fetch.jina import JinaFetchProvider

__all__ = [
    "FetchProvider",
    "FetchResult",
    "FirecrawlFetchProvider",
    "JinaFetchProvider",
]
