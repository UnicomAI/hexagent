"""Unicrawl fetch provider.

Uses Unicrawl API (Firecrawl-compatible) for web scraping.
"""

from __future__ import annotations

import json
import os

import httpx

from hexagent.exceptions import ConfigurationError, WebAPIError
from hexagent.tools.web._markdown import strip_links_and_images
from hexagent.tools.web.providers._retry import web_retry
from hexagent.tools.web.providers.fetch.base import FetchResult

UNICRAWL_API_URL = "https://maas.ai-yuanjing.com/app/firecrawl/v2/scrape"


class UnicrawlFetchProvider:
    """Fetch provider using Unicrawl API.

    Unicrawl handles JavaScript rendering and converts pages to markdown.
    Requires an API key.

    Examples:
        ```python
        provider = UnicrawlFetchProvider()
        result = await provider.fetch("https://example.com")
        print(result.content)
        ```
    """

    name: str = "unicrawl"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            api_key: Unicrawl API key. Falls back to UNICRAWL_API_KEY
                environment variable.
            timeout: Request timeout in seconds.
            client: Optional httpx.AsyncClient for connection pooling.

        Raises:
            ConfigurationError: If no API key is available.
        """
        resolved_key = api_key or os.environ.get("UNICRAWL_API_KEY")
        if not resolved_key:
            msg = "UNICRAWL_API_KEY not set. Get your key from Unicrawl service."
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
        payload = {
            "url": url,
            "onlyMainContent": False,
            "maxAge": 172800000,  # 2 days cache
            "formats": ["markdown"],
        }

        if self._client:
            response = await self._client.post(
                UNICRAWL_API_URL,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    UNICRAWL_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=self._timeout,
                )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise WebAPIError(f"Unicrawl: {e}") from e

        try:
            data = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise WebAPIError("Unicrawl: invalid JSON response") from e

        # Unicrawl returns content directly or in data.markdown
        if isinstance(data, dict):
            # Check for error response
            if not data.get("success", True):
                error_msg = data.get("error", "Unknown error")
                raise WebAPIError(f"Unicrawl: {error_msg}")

            # Response format: { content: "...", metadata: { ... } }
            content = data.get("content", "")
            if not content and "data" in data:
                # Alternative format: { data: { markdown: "..." } }
                inner = data.get("data", {})
                content = inner.get("markdown", "")

            metadata = data.get("metadata", {})
            source_url = metadata.get("sourceURL", url) if isinstance(metadata, dict) else url
            title = metadata.get("title", "") if isinstance(metadata, dict) else ""
        else:
            content = str(data)
            source_url = url
            title = ""

        return FetchResult(
            content=strip_links_and_images(content) if content else "",
            url=source_url,
            title=title or None,
            provider=self.name,
        )
