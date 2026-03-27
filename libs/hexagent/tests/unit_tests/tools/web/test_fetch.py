"""Tests for WebFetchTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from hexagent.exceptions import ConfigurationError, ToolError, WebAPIError
from hexagent.tools.web import WebFetchTool, clear_caches
from hexagent.tools.web.providers.fetch import FetchResult


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear caches before each test."""
    clear_caches()


class TestWebFetchToolExecution:
    """Tests for WebFetchTool execution."""

    async def test_returns_content(self) -> None:
        """Fetch returns the page content."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content="# Hello World\n\nThis is the page content.",
                url="https://example.com",
                title="Hello World",
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")

        assert result.output is not None
        assert result.error is None
        assert "Hello World" in result.output
        assert "This is the page content" in result.output

    async def test_includes_title_when_available(self) -> None:
        """Output includes title header when available."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content="Page content here.",
                url="https://example.com/page",
                title="Page Title",
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com/page")

        assert result.output is not None
        assert "# Page Title" in result.output

    async def test_no_title_omits_header(self) -> None:
        """Output omits title header when not available."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content="Just the content.",
                url="https://example.com",
                title=None,
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")

        assert result.output is not None
        assert result.output == "Just the content."

    async def test_passes_url_to_provider(self) -> None:
        """URL is passed to the provider."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(return_value=FetchResult(content="x", url="", title=None))

        tool = WebFetchTool(provider)
        await tool(url="https://example.com/test")

        provider.fetch.assert_called_once_with("https://example.com/test")

    async def test_empty_content_returns_message(self) -> None:
        """Empty content returns a 'no content' message."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content="",
                url="https://example.com",
                title=None,
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")

        assert result.output == "Page returned no content."
        assert result.error is None

    async def test_caches_fetch_result(self) -> None:
        """Same URL returns cached result without calling provider again."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content="Cached content",
                url="https://example.com",
                title=None,
            )
        )

        tool = WebFetchTool(provider)

        # First call
        await tool(url="https://example.com/cached")
        # Second call with same URL
        await tool(url="https://example.com/cached")

        # Provider should only be called once
        assert provider.fetch.call_count == 1


class TestWebFetchToolErrors:
    """Tests for WebFetchTool error handling."""

    async def test_http_error_raises_tool_error(self) -> None:
        """HTTP errors raise ToolError."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(side_effect=httpx.HTTPError("Connection refused"))

        tool = WebFetchTool(provider)

        with pytest.raises(ToolError):
            await tool(url="https://example.com")

    async def test_web_api_error_wrapped_as_tool_error(self) -> None:
        """WebAPIError is wrapped as ToolError."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(side_effect=WebAPIError("Provider error"))

        tool = WebFetchTool(provider)

        with pytest.raises(ToolError, match="Fetch provider"):
            await tool(url="https://example.com")

    async def test_configuration_error_wrapped_as_tool_error(self) -> None:
        """ConfigurationError is wrapped as ToolError."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.fetch = AsyncMock(side_effect=ConfigurationError("API key missing"))

        tool = WebFetchTool(provider)

        with pytest.raises(ToolError, match="Fetch provider"):
            await tool(url="https://example.com")


class TestWebFetchToolTruncation:
    """Tests for content truncation behavior."""

    async def test_long_content_is_truncated(self) -> None:
        """Content longer than 100K characters is truncated."""
        provider = AsyncMock()
        provider.name = "mock"
        # Create content > 100K characters with paragraph boundaries
        long_content = "This is a paragraph.\n\n" * 10000  # ~220K characters
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content=long_content,
                url="https://example.com",
                title=None,
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")

        assert result.output is not None
        # Should be truncated (less than original)
        assert len(result.output) < len(long_content)

    async def test_short_content_not_truncated(self) -> None:
        """Content shorter than 100K is not truncated."""
        provider = AsyncMock()
        provider.name = "mock"
        short_content = "Short content here."
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content=short_content,
                url="https://example.com",
                title=None,
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")

        assert result.output == short_content

    async def test_truncation_notice_included(self) -> None:
        """Truncated content includes a truncation notice."""
        provider = AsyncMock()
        provider.name = "mock"
        long_content = "x" * 150_000  # 150K characters, no boundaries
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content=long_content,
                url="https://example.com",
                title=None,
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")

        assert result.output is not None
        assert "[Content truncated:" in result.output
        assert "of 150,000 characters]" in result.output


class TestWebFetchToolURLValidation:
    """Tests for URL validation (SSRF prevention)."""

    async def test_private_ip_rejected(self) -> None:
        """Private IP addresses are rejected."""
        provider = AsyncMock()
        tool = WebFetchTool(provider)

        result = await tool(url="http://192.168.1.1/admin")

        assert result.error is not None
        assert result.output is None
        # Provider should NOT be called
        provider.fetch.assert_not_called()

    async def test_localhost_rejected(self) -> None:
        """Localhost URLs are rejected."""
        provider = AsyncMock()
        tool = WebFetchTool(provider)

        result = await tool(url="http://localhost/admin")

        assert result.error is not None
        assert result.output is None
        provider.fetch.assert_not_called()

    async def test_non_http_scheme_rejected(self) -> None:
        """Non-HTTP schemes are rejected."""
        provider = AsyncMock()
        tool = WebFetchTool(provider)

        result = await tool(url="file:///etc/passwd")

        assert result.error is not None
        assert result.output is None
        provider.fetch.assert_not_called()


class TestWebFetchToolSizeLimit:
    """Tests for content size limit."""

    async def test_oversized_content_returns_error(self) -> None:
        """Content exceeding 10MB returns an error."""
        provider = AsyncMock()
        provider.name = "mock"
        # Create content > 10MB (use simple bytes to hit UTF-8 size limit)
        oversized_content = "x" * (11 * 1024 * 1024)  # 11MB
        provider.fetch = AsyncMock(
            return_value=FetchResult(
                content=oversized_content,
                url="https://example.com",
                title=None,
            )
        )

        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")

        assert result.error is not None
        assert "10MB" in result.error
        assert result.output is None


class TestWebFetchToolCacheIsolation:
    """Tests for provider-specific cache isolation."""

    async def test_different_providers_do_not_share_cache(self) -> None:
        """Different providers with same URL have separate cache entries."""
        provider1 = AsyncMock()
        provider1.name = "provider1"
        provider1.fetch = AsyncMock(
            return_value=FetchResult(
                content="Content from Provider 1",
                url="https://example.com",
                title=None,
                provider="provider1",
            )
        )

        provider2 = AsyncMock()
        provider2.name = "provider2"
        provider2.fetch = AsyncMock(
            return_value=FetchResult(
                content="Content from Provider 2",
                url="https://example.com",
                title=None,
                provider="provider2",
            )
        )

        tool1 = WebFetchTool(provider1)
        tool2 = WebFetchTool(provider2)

        # Both tools fetch same URL
        result1 = await tool1(url="https://example.com")
        result2 = await tool2(url="https://example.com")

        # Both providers should be called (no cross-pollution)
        assert provider1.fetch.call_count == 1
        assert provider2.fetch.call_count == 1

        # Results should be from respective providers
        assert result1.output is not None
        assert result2.output is not None
        assert "Provider 1" in result1.output
        assert "Provider 2" in result2.output
