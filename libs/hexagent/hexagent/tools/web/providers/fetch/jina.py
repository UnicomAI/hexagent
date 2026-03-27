"""Jina Reader fetch provider.

Uses Jina's free Reader API to convert web pages to clean text.
"""

from __future__ import annotations

import json
import os

import httpx

from hexagent.exceptions import WebAPIError
from hexagent.tools.web.providers._retry import web_retry
from hexagent.tools.web.providers.fetch.base import FetchResult

JINA_READER_URL = "https://r.jina.ai/"


class JinaFetchProvider:
    """Fetch provider using Jina Reader API.

    Jina Reader converts web pages to clean, LLM-friendly text.
    Works without an API key (with lower rate limits).

    Examples:
        ```python
        provider = JinaFetchProvider()
        result = await provider.fetch("https://example.com")
        print(result.content)
        ```
    """

    name: str = "jina"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            api_key: Optional Jina API key for higher rate limits.
                Falls back to JINA_API_KEY environment variable.
            timeout: Request timeout in seconds.
            client: Optional httpx.AsyncClient for connection pooling.
        """
        self._api_key = api_key or os.environ.get("JINA_API_KEY")
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
        headers: dict[str, str] = {
            "Accept": "application/json",
            "X-Retain-Images": "none",
            "X-Md-Link-Style": "discarded",
            "X-Base": "final",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        if self._client:
            response = await self._client.get(
                f"{JINA_READER_URL}{url}",
                headers=headers,
                follow_redirects=True,
                timeout=self._timeout,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{JINA_READER_URL}{url}",
                    headers=headers,
                    follow_redirects=True,
                    timeout=self._timeout,
                )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise WebAPIError(f"Jina: {e}") from e

        try:
            body = response.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise WebAPIError("Jina: invalid JSON response") from e

        data = body.get("data") or {}

        return FetchResult(
            content=data.get("content", ""),
            url=data.get("url", ""),
            title=data.get("title", ""),
            provider=self.name,
        )
