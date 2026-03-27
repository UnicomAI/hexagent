"""Firecrawl fetch provider.

Uses Firecrawl API for advanced web scraping with JavaScript rendering.
"""

from __future__ import annotations

import json
import os

import httpx

from hexagent.exceptions import ConfigurationError, WebAPIError
from hexagent.tools.web._markdown import strip_links_and_images
from hexagent.tools.web.providers._retry import web_retry
from hexagent.tools.web.providers.fetch.base import FetchResult

FIRECRAWL_API_URL = "https://api.firecrawl.dev/v1/scrape"


class FirecrawlFetchProvider:
    """Fetch provider using Firecrawl API.

    Firecrawl handles JavaScript rendering and converts pages to markdown.
    Requires an API key.

    Examples:
        ```python
        provider = FirecrawlFetchProvider()
        result = await provider.fetch("https://example.com")
        print(result.content)
        ```
    """

    name: str = "firecrawl"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            api_key: Firecrawl API key. Falls back to FIRECRAWL_API_KEY
                environment variable.
            timeout: Request timeout in seconds.
            client: Optional httpx.AsyncClient for connection pooling.

        Raises:
            ConfigurationError: If no API key is available.
        """
        resolved_key = api_key or os.environ.get("FIRECRAWL_API_KEY")
        if not resolved_key:
            msg = "FIRECRAWL_API_KEY not set. Get your key at https://firecrawl.dev"
            raise ConfigurationError(msg)
        self._api_key = resolved_key
        self._timeout = timeout
        self._client = client

    @web_retry
    async def fetch(self, url: str) -> FetchResult:
        """Fetch and extract content from a URL.

        Args:
            url: The URL to fetch.

        Returns:
            FetchResult with extracted content.
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {"url": url, "formats": ["markdown"]}

        if self._client:
            response = await self._client.post(
                FIRECRAWL_API_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    FIRECRAWL_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise WebAPIError(f"Firecrawl: {e}") from e

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise WebAPIError("Firecrawl: invalid JSON response") from e

        if not data.get("success", True):
            raise WebAPIError(f"Firecrawl: 'success' is false in response. Raw: {data}")

        result_data = data.get("data") or {}
        metadata = result_data.get("metadata") or {}

        return FetchResult(
            content=strip_links_and_images(result_data.get("markdown", "")),
            url=metadata.get("sourceURL", ""),
            title=metadata.get("title", ""),
            provider=self.name,
        )
