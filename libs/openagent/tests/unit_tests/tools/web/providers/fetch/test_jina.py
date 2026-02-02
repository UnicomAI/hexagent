"""Tests for JinaFetchProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from openagent.exceptions import WebAPIError
from openagent.tools.web.providers.fetch.jina import JinaFetchProvider


class TestJinaFetchProvider:
    """Tests for JinaFetchProvider behavior."""

    # Happy paths

    async def test_fetch_returns_content_title_url(self) -> None:
        """Fetch returns content, title, and url from API response."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "content": "# Page Title\n\nPage content here.",
                "url": "https://example.com/page",
                "title": "Page Title",
            }
        }
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = JinaFetchProvider(api_key="test-key", client=mock_client)
        result = await provider.fetch("https://example.com/page")

        assert result.content == "# Page Title\n\nPage content here."
        assert result.url == "https://example.com/page"
        assert result.title == "Page Title"

    async def test_works_without_api_key(self) -> None:
        """Jina works without an API key (lower rate limits)."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"content": "test", "url": "", "title": ""}}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        # Should not raise ConfigurationError
        provider = JinaFetchProvider(client=mock_client)
        result = await provider.fetch("https://example.com")

        assert result.content == "test"

    async def test_api_key_adds_authorization_header(self) -> None:
        """API key is sent as Authorization header when provided."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": {"content": "test", "url": "", "title": ""}}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = JinaFetchProvider(api_key="my-secret-key", client=mock_client)
        await provider.fetch("https://example.com")

        # Verify Authorization header was included
        call_kwargs = mock_client.get.call_args.kwargs
        assert "Authorization" in call_kwargs["headers"]
        assert call_kwargs["headers"]["Authorization"] == "Bearer my-secret-key"

    def test_api_key_from_environment_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Provider reads API key from environment variable."""
        monkeypatch.setenv("JINA_API_KEY", "env-key")
        provider = JinaFetchProvider()
        assert provider._api_key == "env-key"

    # Unhappy paths

    async def test_http_error_raises_web_api_error(self) -> None:
        """HTTP errors raise WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response)
        mock_client.get.return_value = mock_response

        provider = JinaFetchProvider(api_key="test-key", client=mock_client)

        with pytest.raises(WebAPIError, match="Jina"):
            await provider.fetch("https://example.com")

    async def test_invalid_json_raises_web_api_error(self) -> None:
        """Invalid JSON response raises WebAPIError."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_client.get.return_value = mock_response

        provider = JinaFetchProvider(api_key="test-key", client=mock_client)

        with pytest.raises(WebAPIError, match="invalid JSON"):
            await provider.fetch("https://example.com")

    async def test_missing_data_field_returns_empty_strings(self) -> None:
        """Missing data field returns empty strings."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # Missing "data" field
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = JinaFetchProvider(api_key="test-key", client=mock_client)
        result = await provider.fetch("https://example.com")

        assert result.content == ""
        assert result.url == ""
        assert result.title == ""

    async def test_null_data_returns_empty_strings(self) -> None:
        """Null data field returns empty strings."""
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": None}
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response

        provider = JinaFetchProvider(api_key="test-key", client=mock_client)
        result = await provider.fetch("https://example.com")

        assert result.content == ""
        assert result.url == ""
        assert result.title == ""
