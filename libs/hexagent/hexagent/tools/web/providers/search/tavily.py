"""Tavily search provider.

Uses Tavily's AI-powered search API designed for LLM agents.
"""

from __future__ import annotations

import json
import os

import httpx

from hexagent.exceptions import ConfigurationError, WebAPIError
from hexagent.tools.web.providers._retry import web_retry
from hexagent.tools.web.providers.search.base import SearchResult, SearchResultItem

TAVILY_API_URL = "https://api.tavily.com/search"


class TavilySearchProvider:
    """Search provider using Tavily API.

    Tavily provides AI-optimized search results for agents.
    Requires an API key.

    Examples:
        ```python
        provider = TavilySearchProvider()
        results = await provider.search("python async programming")
        for item in results:
            print(f"{item.title}: {item.url}")
        ```
    """

    name: str = "tavily"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            api_key: Tavily API key. Falls back to TAVILY_API_KEY
                environment variable.
            timeout: Request timeout in seconds.
            client: Optional httpx.AsyncClient for connection pooling.

        Raises:
            ConfigurationError: If no API key is available.
        """
        resolved_key = api_key or os.environ.get("TAVILY_API_KEY")
        if not resolved_key:
            msg = "TAVILY_API_KEY not set. Get your key at https://tavily.com"
            raise ConfigurationError(msg)
        self._api_key = resolved_key
        self._timeout = timeout
        self._client = client

    @web_retry
    async def search(self, query: str, *, max_results: int = 10) -> SearchResult:
        """Search the web.

        Args:
            query: The search query.
            max_results: Maximum number of results to return.

        Returns:
            SearchResult containing items and optional AI summary.
        """
        payload = {
            "api_key": self._api_key,
            "query": query,
            "max_results": max_results,
            "include_answer": "basic",
        }

        if self._client:
            response = await self._client.post(TAVILY_API_URL, json=payload, timeout=self._timeout)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(TAVILY_API_URL, json=payload, timeout=self._timeout)

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise WebAPIError(f"Tavily: {e}") from e

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise WebAPIError("Tavily: invalid JSON response") from e

        items = [
            SearchResultItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("content", ""),
                date=None,  # Tavily API does not provide publication dates
            )
            for item in data.get("results", [])
        ]

        return SearchResult(
            items=items,
            ai_summary=data.get("answer"),
            provider="tavily",
            raw=data,
        )
