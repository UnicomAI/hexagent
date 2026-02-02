"""Brave search provider.

Uses Brave's privacy-focused search API.
"""

from __future__ import annotations

import json
import os

import httpx

from openagent.exceptions import ConfigurationError, WebAPIError
from openagent.tools.web.providers._retry import web_retry
from openagent.tools.web.providers.search.base import (
    SearchResult,
    SearchResultItem,
    parse_date,
)

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider:
    """Search provider using Brave Search API.

    Brave Search has its own independent index and focuses on privacy.
    Requires an API key.

    Examples:
        ```python
        provider = BraveSearchProvider()
        results = await provider.search("python async programming")
        for item in results:
            print(f"{item.title}: {item.url}")
        ```
    """

    name: str = "brave"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            api_key: Brave API key. Falls back to BRAVE_API_KEY
                environment variable.
            timeout: Request timeout in seconds.
            client: Optional httpx.AsyncClient for connection pooling.

        Raises:
            ConfigurationError: If no API key is available.
        """
        resolved_key = api_key or os.environ.get("BRAVE_API_KEY")
        if not resolved_key:
            msg = "BRAVE_API_KEY not set. Get your key at https://brave.com/search/api/"
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
            SearchResult containing items (no AI summary for basic web search).
        """
        params: dict[str, str | int] = {"q": query, "count": max_results, "extra_snippets": "true"}
        headers = {
            "X-Subscription-Token": self._api_key,
            "Accept": "application/json",
        }

        if self._client:
            response = await self._client.get(
                BRAVE_API_URL,
                params=params,
                headers=headers,
                timeout=self._timeout,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    BRAVE_API_URL,
                    params=params,
                    headers=headers,
                    timeout=self._timeout,
                )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise WebAPIError(f"Brave: {e}") from e

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise WebAPIError("Brave: invalid JSON response") from e

        web = data.get("web") or {}
        web_results = web.get("results") or []
        items = [
            SearchResultItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=("\n".join(item["extra_snippets"]) if item.get("extra_snippets") else item.get("description", "")),
                date=parse_date(item.get("page_age")),
            )
            for item in web_results
        ]

        return SearchResult(
            items=items,
            ai_summary=None,
            provider="brave",
            raw=data,
        )
