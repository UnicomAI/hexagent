"""Tests for FirecrawlFetchProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from openagent.exceptions import ConfigurationError, WebAPIError
from openagent.tools.web.providers.fetch.firecrawl import FirecrawlFetchProvider


class TestFirecrawlFetchProvider:
    """Tests for FirecrawlFetchProvider behavior."""

    # Happy paths

    async def test_fetch_returns_markdown_content(self) -> None:
        """Fetch returns markdown content from API response."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "markdown": "# Page Title\n\nContent here.",
                "metadata": {"sourceURL": "https://example.com", "title": "Page Title"},
            },
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = FirecrawlFetchProvider(api_key="test-key", client=mock_client)
        result = await provider.fetch("https://example.com")

        assert result.content == "# Page Title\n\nContent here."
        assert result.url == "https://example.com"
        assert result.title == "Page Title"

    async def test_extracts_title_from_metadata(self) -> None:
        """Title is extracted from metadata."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "data": {
                "markdown": "content",
                "metadata": {"title": "My Page Title", "sourceURL": ""},
            },
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = FirecrawlFetchProvider(api_key="test-key", client=mock_client)
        result = await provider.fetch("https://example.com")

        assert result.title == "My Page Title"

    def test_api_key_from_environment_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provider reads API key from environment variable."""
        monkeypatch.setenv("FIRECRAWL_API_KEY", "env-key")
        provider = FirecrawlFetchProvider()
        assert provider._api_key == "env-key"

    # Unhappy paths

    def test_missing_api_key_raises_configuration_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Missing API key raises ConfigurationError."""
        monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
        with pytest.raises(ConfigurationError, match="FIRECRAWL_API_KEY"):
            FirecrawlFetchProvider()

    async def test_http_error_raises_web_api_error(self) -> None:
        """HTTP errors raise WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=mock_response)
        mock_client.post.return_value = mock_response

        provider = FirecrawlFetchProvider(api_key="bad-key", client=mock_client)

        with pytest.raises(WebAPIError, match="Firecrawl"):
            await provider.fetch("https://example.com")

    async def test_invalid_json_raises_web_api_error(self) -> None:
        """Invalid JSON response raises WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.post.return_value = mock_response

        provider = FirecrawlFetchProvider(api_key="test-key", client=mock_client)

        with pytest.raises(WebAPIError, match="invalid JSON"):
            await provider.fetch("https://example.com")

    async def test_success_false_raises_web_api_error(self) -> None:
        """Response with success=false raises WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": False,
            "error": "Page not found",
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = FirecrawlFetchProvider(api_key="test-key", client=mock_client)

        with pytest.raises(WebAPIError, match="success.*false"):
            await provider.fetch("https://example.com/not-found")

    async def test_missing_metadata_returns_empty_title(self) -> None:
        """Missing metadata returns empty title."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "data": {"markdown": "content"},  # No metadata
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = FirecrawlFetchProvider(api_key="test-key", client=mock_client)
        result = await provider.fetch("https://example.com")

        assert result.title == ""
        assert result.url == ""

    async def test_missing_markdown_returns_empty_content(self) -> None:
        """Missing markdown returns empty content."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "success": True,
            "data": {"metadata": {"title": "x", "sourceURL": "x"}},  # No markdown
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response

        provider = FirecrawlFetchProvider(api_key="test-key", client=mock_client)
        result = await provider.fetch("https://example.com")

        assert result.content == ""
