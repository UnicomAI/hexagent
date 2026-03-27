"""Tests for WebSearchTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from hexagent.exceptions import ConfigurationError, ToolError, WebAPIError
from hexagent.tools.web import WebSearchTool, clear_caches
from hexagent.tools.web.providers.search import SearchResult, SearchResultItem
from hexagent.tools.web.search import MAX_SEARCH_RESULTS


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Clear caches before each test."""
    clear_caches()


class TestWebSearchToolExecution:
    """Tests for WebSearchTool execution."""

    async def test_returns_formatted_results(self) -> None:
        """Search results are formatted with titles, URLs, and snippets."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(
            return_value=SearchResult(
                items=[
                    SearchResultItem(
                        title="Python Tutorial",
                        url="https://example.com/python",
                        snippet="Learn Python programming...",
                    ),
                    SearchResultItem(
                        title="Async Python",
                        url="https://example.com/async",
                        snippet="Async/await patterns...",
                    ),
                ]
            )
        )

        tool = WebSearchTool(provider)
        result = await tool(query="python async")

        assert result.output is not None
        assert result.error is None
        assert "Python Tutorial" in result.output
        assert "https://example.com/python" in result.output
        assert "Learn Python programming" in result.output

    async def test_passes_query_to_provider(self) -> None:
        """Query is passed to the provider with fixed max_results."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(return_value=SearchResult(items=[]))

        tool = WebSearchTool(provider)
        await tool(query="test query")

        provider.search.assert_called_once_with("test query", max_results=MAX_SEARCH_RESULTS)

    async def test_empty_results_returns_message(self) -> None:
        """Empty search results return a 'no results' message."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(return_value=SearchResult(items=[]))

        tool = WebSearchTool(provider)
        result = await tool(query="obscure query")

        assert result.output == 'No results found for query: "obscure query".'
        assert result.error is None

    async def test_caches_search_result(self) -> None:
        """Same query returns cached result without calling provider again."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(
            return_value=SearchResult(
                items=[
                    SearchResultItem(
                        title="Result",
                        url="https://example.com",
                        snippet="Cached",
                    )
                ]
            )
        )

        tool = WebSearchTool(provider)

        # First call
        await tool(query="cached query")
        # Second call with same query
        await tool(query="cached query")

        # Provider should only be called once
        assert provider.search.call_count == 1


class TestWebSearchToolErrors:
    """Tests for WebSearchTool error handling."""

    async def test_http_error_raises_tool_error(self) -> None:
        """HTTP errors raise ToolError."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(side_effect=httpx.HTTPError("API rate limited"))

        tool = WebSearchTool(provider)

        with pytest.raises(ToolError):
            await tool(query="test query")

    async def test_configuration_error_raises_tool_error(self) -> None:
        """Configuration errors raise ToolError."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(side_effect=ConfigurationError("TAVILY_API_KEY not set"))

        tool = WebSearchTool(provider)

        with pytest.raises(ToolError):
            await tool(query="test")

    async def test_web_api_error_wrapped_as_tool_error(self) -> None:
        """WebAPIError is wrapped as ToolError."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(side_effect=WebAPIError("Provider error"))

        tool = WebSearchTool(provider)

        with pytest.raises(ToolError, match="Search provider"):
            await tool(query="test")


class TestWebSearchToolOutput:
    """Tests for WebSearchTool output formatting."""

    async def test_output_with_ai_summary_includes_json_links_and_summary(self) -> None:
        """Output with AI summary uses compact format: JSON links + summary."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(
            return_value=SearchResult(
                items=[
                    SearchResultItem(title="Result 1", url="https://example.com/1", snippet="Snippet 1"),
                    SearchResultItem(title="Result 2", url="https://example.com/2", snippet="Snippet 2"),
                ],
                ai_summary="This is the AI-generated summary.",
            )
        )

        tool = WebSearchTool(provider)
        result = await tool(query="test query")

        assert result.output is not None
        # Should include query intro
        assert 'Web search results for query: "test query"' in result.output
        # Should include AI summary
        assert "This is the AI-generated summary." in result.output
        # Should include links as JSON (compact format)
        assert '"title": "Result 1"' in result.output
        assert '"url": "https://example.com/1"' in result.output
        # Snippets should NOT be in compact format (only in detailed format)
        assert "Snippet 1" not in result.output

    async def test_output_without_ai_summary_includes_full_snippets(self) -> None:
        """Output without AI summary uses detailed format with full snippets."""
        provider = AsyncMock()
        provider.name = "mock"
        provider.search = AsyncMock(
            return_value=SearchResult(
                items=[
                    SearchResultItem(title="Result 1", url="https://example.com/1", snippet="Detailed snippet 1"),
                    SearchResultItem(title="Result 2", url="https://example.com/2", snippet="Detailed snippet 2"),
                ],
                ai_summary=None,
            )
        )

        tool = WebSearchTool(provider)
        result = await tool(query="test query")

        assert result.output is not None
        # Should include full result blocks with snippets
        assert "Title: Result 1" in result.output
        assert "URL: https://example.com/1" in result.output
        assert "Detailed snippet 1" in result.output
        assert "Title: Result 2" in result.output
        assert "Detailed snippet 2" in result.output
        # Blocks separated by ---
        assert "---" in result.output


class TestWebSearchToolCacheIsolation:
    """Tests for provider-specific cache isolation."""

    async def test_different_providers_do_not_share_cache(self) -> None:
        """Different providers with same query have separate cache entries."""
        provider1 = AsyncMock()
        provider1.name = "provider1"
        provider1.search = AsyncMock(
            return_value=SearchResult(
                items=[
                    SearchResultItem(
                        title="From Provider 1",
                        url="https://example.com/1",
                        snippet="Result from provider 1",
                    )
                ],
                provider="provider1",
            )
        )

        provider2 = AsyncMock()
        provider2.name = "provider2"
        provider2.search = AsyncMock(
            return_value=SearchResult(
                items=[
                    SearchResultItem(
                        title="From Provider 2",
                        url="https://example.com/2",
                        snippet="Result from provider 2",
                    )
                ],
                provider="provider2",
            )
        )

        tool1 = WebSearchTool(provider1)
        tool2 = WebSearchTool(provider2)

        # Both tools search with same query
        result1 = await tool1(query="test query")
        result2 = await tool2(query="test query")

        # Both providers should be called (no cross-pollution)
        assert provider1.search.call_count == 1
        assert provider2.search.call_count == 1

        # Results should be from respective providers
        assert result1.output is not None
        assert result2.output is not None
        assert "Provider 1" in result1.output
        assert "Provider 2" in result2.output
