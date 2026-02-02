"""Tests for TavilySearchProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from openagent.exceptions import ConfigurationError, WebAPIError
from openagent.tools.web.providers.search.tavily import TavilySearchProvider


class TestTavilySearchProvider:
    """Tests for TavilySearchProvider behavior."""

    # Happy paths

    async def test_search_returns_items_from_api_response(self) -> None:
        """Search returns items from API response."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"title": "Python Docs", "url": "https://python.org", "content": "Official Python documentation."},
                {"title": "Real Python", "url": "https://realpython.com", "content": "Python tutorials."},
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("python")

        expected_count = 2
        assert len(result.items) == expected_count
        assert result.items[0].title == "Python Docs"
        assert result.items[0].url == "https://python.org"
        assert result.items[0].snippet == "Official Python documentation."
        assert result.provider == "tavily"

    async def test_search_includes_ai_summary_when_present(self) -> None:
        """AI summary is included when API returns an answer."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [],
            "answer": "Python is a programming language.",
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("what is python")

        assert result.ai_summary == "Python is a programming language."

    async def test_search_returns_none_ai_summary_when_absent(self) -> None:
        """AI summary is None when API doesn't return an answer."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("query")

        assert result.ai_summary is None

    def test_api_key_from_environment_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provider reads API key from environment variable."""
        monkeypatch.setenv("TAVILY_API_KEY", "env-key")
        provider = TavilySearchProvider()
        assert provider._api_key == "env-key"

    # Unhappy paths

    def test_missing_api_key_raises_configuration_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing API key raises ConfigurationError."""
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="TAVILY_API_KEY"):
            TavilySearchProvider()

    async def test_http_401_raises_web_api_error(self) -> None:
        """HTTP 401 raises WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="bad-key", client=mock_client)

        with pytest.raises(WebAPIError, match="Tavily"):
            await provider.search("query")

    async def test_http_500_raises_web_api_error(self) -> None:
        """HTTP 500 raises WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="test-key", client=mock_client)

        with pytest.raises(WebAPIError, match="Tavily"):
            await provider.search("query")

    async def test_invalid_json_response_raises_web_api_error(self) -> None:
        """Invalid JSON response raises WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="test-key", client=mock_client)

        with pytest.raises(WebAPIError, match="invalid JSON"):
            await provider.search("query")

    async def test_empty_results_array_returns_empty_items(self) -> None:
        """Empty results array returns empty items list."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("obscure query")

        assert result.items == []

    async def test_malformed_result_item_uses_defaults(self) -> None:
        """Malformed result items use empty string defaults."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{}]  # Missing all fields
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = TavilySearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("query")

        assert len(result.items) == 1
        assert result.items[0].title == ""
        assert result.items[0].url == ""
        assert result.items[0].snippet == ""
