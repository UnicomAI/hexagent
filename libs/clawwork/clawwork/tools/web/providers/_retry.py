"""Shared retry configuration for web providers.

Uses tenacity for retry logic with exponential backoff.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


def _should_retry(exc: BaseException) -> bool:
    """Determine if exception is retryable.

    Retries on:
    - Connection errors (network issues)
    - Timeouts (read/write)
    - HTTP 429 (rate limit) and 5xx (server errors)
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


web_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(_should_retry),
    reraise=True,
)
"""Decorator for retrying web requests with exponential backoff.

Usage:
    @web_retry
    async def fetch(self, url: str) -> FetchResult:
        ...
"""
