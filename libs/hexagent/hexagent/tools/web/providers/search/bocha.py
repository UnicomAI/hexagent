"""Bocha search provider.

Uses Bocha's AI-optimized search API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from hexagent.exceptions import ConfigurationError, WebAPIError
from hexagent.tools.web.providers._retry import web_retry
from hexagent.tools.web.providers.search.base import (
    SearchResult,
    SearchResultItem,
    parse_date,
)

BOCHA_API_URL = "https://api.bocha.cn/v1/web-search"


class BochaSearchProvider:
    """Search provider using Bocha Search API.

    Bocha provides AI-optimized search results.
    Requires an API key.

    Examples:
        ```python
        provider = BochaSearchProvider()
        results = await provider.search("python async programming")
        for item in results:
            print(f"{item.title}: {item.url}")
        ```
    """

    name: str = "bocha"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            api_key: Bocha API key. Falls back to BOCHA_API_KEY
                environment variable.
            timeout: Request timeout in seconds.
            client: Optional httpx.AsyncClient for connection pooling.

        Raises:
            ConfigurationError: If no API key is available.
        """
        resolved_key = api_key or os.environ.get("BOCHA_API_KEY")
        if not resolved_key:
            msg = "BOCHA_API_KEY not set. Get your key at https://open.bocha.cn"
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
        logger = logging.getLogger(__name__)
        logger.info(f"Bocha searching: '{query}' (max_results={max_results})")
        
        payload = {
            "query": query,
            "count": max_results,
            "summary": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._client:
                response = await self._client.post(
                    BOCHA_API_URL, json=payload, headers=headers, timeout=self._timeout
                )
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        BOCHA_API_URL, json=payload, headers=headers, timeout=self._timeout
                    )
            
            response.raise_for_status()
            data = response.json()
            
            if data.get("code") != 200:
                error_msg = data.get("msg") or data.get("message")
                logger.error(f"Bocha API error {data.get('code')}: {error_msg}")
                raise WebAPIError(f"Bocha error {data.get('code')}: {error_msg}")
            
            search_data = data.get("data") or {}
            web_pages = search_data.get("webPages") or {}
            values = web_pages.get("value") or []
            
            logger.debug(f"Bocha returned {len(values)} results")

            items = [
                SearchResultItem(
                    title=item.get("name", ""),
                    url=item.get("url", ""),
                    snippet=item.get("summary") or item.get("snippet", ""),
                    date=parse_date(item.get("datePublished")),
                )
                for item in values
            ]
            
            return SearchResult(
                items=items,
                ai_summary=None,
                provider="bocha",
                raw=data,
            )
            
        except httpx.HTTPStatusError as e:
            try:
                error_data = e.response.json()
                error_msg = error_data.get("message") or str(e)
            except Exception:
                error_msg = str(e)
            logger.error(f"Bocha HTTP error: {error_msg}")
            raise WebAPIError(f"Bocha: {error_msg}") from e
        except Exception as e:
            if not isinstance(e, WebAPIError):
                logger.exception(f"Unexpected error in BochaSearchProvider: {e}")
            raise
