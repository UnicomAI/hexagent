"""Tests for retry behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from openagent.tools.web.providers._retry import _should_retry, web_retry

# Known retry configuration values
MAX_RETRY_ATTEMPTS = 3


def _make_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Create an HTTPStatusError with the given status code."""
    response = MagicMock()
    response.status_code = status_code
    msg = f"HTTP {status_code}"
    return httpx.HTTPStatusError(msg, request=MagicMock(), response=response)


class TestShouldRetry:
    """Tests for _should_retry function - determines which errors trigger retries."""

    # Retryable conditions

    def test_connect_error_triggers_retry(self) -> None:
        """Connection errors should be retried."""
        exc = httpx.ConnectError(message="test")
        assert _should_retry(exc) is True

    def test_read_timeout_triggers_retry(self) -> None:
        """Read timeouts should be retried."""
        exc = httpx.ReadTimeout(message="test")
        assert _should_retry(exc) is True

    def test_write_timeout_triggers_retry(self) -> None:
        """Write timeouts should be retried."""
        exc = httpx.WriteTimeout(message="test")
        assert _should_retry(exc) is True

    def test_http_429_triggers_retry(self) -> None:
        """Rate limit (429) errors should be retried."""
        exc = _make_http_status_error(429)
        assert _should_retry(exc) is True

    def test_http_500_triggers_retry(self) -> None:
        """Server errors (500) should be retried."""
        exc = _make_http_status_error(500)
        assert _should_retry(exc) is True

    def test_http_503_triggers_retry(self) -> None:
        """Service unavailable (503) should be retried."""
        exc = _make_http_status_error(503)
        assert _should_retry(exc) is True

    # Non-retryable conditions

    def test_http_400_does_not_retry(self) -> None:
        """Bad request (400) should not be retried."""
        exc = _make_http_status_error(400)
        assert _should_retry(exc) is False

    def test_http_401_does_not_retry(self) -> None:
        """Unauthorized (401) should not be retried."""
        exc = _make_http_status_error(401)
        assert _should_retry(exc) is False

    def test_http_403_does_not_retry(self) -> None:
        """Forbidden (403) should not be retried."""
        exc = _make_http_status_error(403)
        assert _should_retry(exc) is False

    def test_http_404_does_not_retry(self) -> None:
        """Not found (404) should not be retried."""
        exc = _make_http_status_error(404)
        assert _should_retry(exc) is False

    def test_value_error_does_not_retry(self) -> None:
        """Non-HTTP errors should not be retried."""
        exc = ValueError("test")
        assert _should_retry(exc) is False


class TestWebRetryDecorator:
    """Tests for web_retry decorator behavior."""

    async def test_gives_up_after_max_attempts(self) -> None:
        """Stops retrying after max attempts."""
        call_count = 0

        @web_retry
        async def always_fails() -> None:
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError(message="test")

        with pytest.raises(httpx.ConnectError):
            await always_fails()

        assert call_count == MAX_RETRY_ATTEMPTS

    async def test_original_exception_is_reraised(self) -> None:
        """The original exception type is preserved, not wrapped."""

        @web_retry
        async def fails_once() -> None:
            raise httpx.ReadTimeout(message="test")

        with pytest.raises(httpx.ReadTimeout):
            await fails_once()

    async def test_non_retryable_error_fails_immediately(self) -> None:
        """Non-retryable errors don't trigger retry attempts."""
        call_count = 0

        @web_retry
        async def bad_request() -> None:
            nonlocal call_count
            call_count += 1
            raise _make_http_status_error(400)

        with pytest.raises(httpx.HTTPStatusError):
            await bad_request()

        assert call_count == 1  # Only called once, no retries

    async def test_succeeds_after_transient_failure(self) -> None:
        """Succeeds when transient failures are followed by success."""
        call_count = 0

        @web_retry
        async def fails_twice_then_succeeds() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < MAX_RETRY_ATTEMPTS:
                raise httpx.ConnectError(message="test")
            return "success"

        result = await fails_twice_then_succeeds()

        assert result == "success"
        assert call_count == MAX_RETRY_ATTEMPTS
