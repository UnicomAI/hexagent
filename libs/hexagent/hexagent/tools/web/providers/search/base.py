"""Base protocol and types for search providers.

This module defines the SearchProvider protocol and result types that
all search provider implementations must follow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable


def parse_date(value: str | None) -> date | None:
    """Parse an ISO date string to a date object.

    Args:
        value: ISO format date/datetime string (e.g., '2025-11-28' or '2025-11-28T00:00:00').

    Returns:
        Date object or None if value is empty or parsing fails.
    """
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


@dataclass(frozen=True, kw_only=True)
class SearchResultItem:
    """A single search result item.

    Attributes:
        title: The title of the search result.
        url: The URL of the search result.
        snippet: A text snippet/excerpt from the result.
        date: Publication or crawl date of the result, if available.
        image_url: Optional URL for an associated image.
        image_title: Optional title/description for the associated image.
    """

    title: str
    url: str
    snippet: str
    date: date | None = None
    image_url: str | None = None
    image_title: str | None = None


@dataclass(frozen=True, kw_only=True)
class SearchResult:
    """Result from a search query.

    Attributes:
        items: List of individual search result items.
        ai_summary: AI-generated summary/answer for the query, if available.
        provider: Name of the search provider that returned this result.
        raw: Raw response data from the provider.
    """

    items: list[SearchResultItem]
    ai_summary: str | None = None
    provider: str | None = None
    raw: dict[str, Any] | None = None


@runtime_checkable
class SearchProvider(Protocol):
    """Protocol for search providers.

    Search providers implement web search functionality using various
    backends (Tavily, Brave, etc.).

    Attributes:
        name: Unique identifier for the provider (used in cache keys).

    Examples:
        ```python
        class MySearchProvider:
            name: str = "my_provider"

            async def search(
                self,
                query: str,
                *,
                max_results: int = 10,
            ) -> SearchResult:
                # Implementation
                ...
        ```
    """

    name: str

    async def search(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> SearchResult:
        """Search the web for the given query.

        Args:
            query: The search query string.
            max_results: Maximum number of results to return.

        Returns:
            SearchResult containing items and optional AI summary.

        Raises:
            ConfigurationError: If required API keys are missing.
            Exception: If the search request fails.
        """
        ...
