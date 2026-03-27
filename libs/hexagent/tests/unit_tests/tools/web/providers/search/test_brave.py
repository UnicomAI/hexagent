"""Tests for BraveSearchProvider."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from hexagent.exceptions import ConfigurationError, WebAPIError
from hexagent.tools.web.providers.search.brave import BraveSearchProvider


class TestBraveSearchProvider:
    """Tests for BraveSearchProvider behavior."""

    # Happy paths

    async def test_search_returns_items_from_api_response(self) -> None:
        """Search returns items from API response."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {"title": "Python Docs", "url": "https://python.org", "description": "Official docs."},
                    {"title": "Real Python", "url": "https://realpython.com", "description": "Tutorials."},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("python")

        expected_count = 2
        assert len(result.items) == expected_count
        assert result.items[0].title == "Python Docs"
        assert result.items[0].url == "https://python.org"
        assert result.provider == "brave"
        # Brave never returns AI summary
        assert result.ai_summary is None

    async def test_parses_extra_snippets_into_snippet(self) -> None:
        """Extra snippets are joined into snippet field."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test",
                        "url": "https://test.com",
                        "extra_snippets": ["First paragraph.", "Second paragraph."],
                    }
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("test")

        assert result.items[0].snippet == "First paragraph.\nSecond paragraph."

    async def test_falls_back_to_description_when_no_snippets(self) -> None:
        """Falls back to description when extra_snippets not present."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"web": {"results": [{"title": "Test", "url": "https://test.com", "description": "Fallback description."}]}}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("test")

        assert result.items[0].snippet == "Fallback description."

    async def test_parses_page_age_into_date(self) -> None:
        """Page age is parsed into date field."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {"results": [{"title": "Test", "url": "https://test.com", "description": "x", "page_age": "2025-01-15"}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("test")

        assert result.items[0].date == date(2025, 1, 15)

    def test_api_key_from_environment_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provider reads API key from environment variable."""
        monkeypatch.setenv("BRAVE_API_KEY", "env-key")
        provider = BraveSearchProvider()
        assert provider._api_key == "env-key"

    # Unhappy paths

    def test_missing_api_key_raises_configuration_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing API key raises ConfigurationError."""
        monkeypatch.delenv("BRAVE_API_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="BRAVE_API_KEY"):
            BraveSearchProvider()

    async def test_http_error_raises_web_api_error(self) -> None:
        """HTTP errors raise WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="bad-key", client=mock_client)

        with pytest.raises(WebAPIError, match="Brave"):
            await provider.search("query")

    async def test_invalid_json_raises_web_api_error(self) -> None:
        """Invalid JSON raises WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)

        with pytest.raises(WebAPIError, match="invalid JSON"):
            await provider.search("query")

    async def test_missing_web_results_returns_empty_items(self) -> None:
        """Missing web.results returns empty items list."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"web": {}}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("query")

        assert result.items == []

    async def test_null_web_object_returns_empty_items(self) -> None:
        """Null web object returns empty items list."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"web": None}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("query")

        assert result.items == []

    async def test_invalid_date_format_returns_none(self) -> None:
        """Invalid date format returns None for date field."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "web": {"results": [{"title": "Test", "url": "https://test.com", "description": "x", "page_age": "not-a-date"}]}
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = BraveSearchProvider(api_key="test-key", client=mock_client)
        result = await provider.search("test")

        assert result.items[0].date is None
