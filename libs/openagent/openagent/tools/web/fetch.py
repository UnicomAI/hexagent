"""Web fetch tool for retrieving content from URLs.

Provides WebFetchTool for agents to fetch and extract web page content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal

import httpx

from openagent.exceptions import ConfigurationError, ToolError, WebAPIError
from openagent.tools.base import BaseAgentTool
from openagent.tools.web._cache import cache_key, get_fetch_cache
from openagent.tools.web._validation import validate_url
from openagent.types import ToolResult, WebFetchToolParams

if TYPE_CHECKING:
    from openagent.tools.web.providers.fetch import FetchProvider

# Content size limits
MAX_CONTENT_SIZE: Final[int] = 10_485_760  # 10MB hard limit
DEFAULT_MAX_CONTENT_LENGTH: Final[int] = 100_000  # 100K characters for truncation
_PARAGRAPH_BOUNDARIES: Final[tuple[str, ...]] = ("\n\n", "\n", ". ", " ")


def _truncate_content(content: str, max_length: int = DEFAULT_MAX_CONTENT_LENGTH) -> tuple[str, bool, int]:
    """Truncate content at natural boundaries.

    Args:
        content: The content to truncate.
        max_length: Maximum length in characters.

    Returns:
        Tuple of (truncated_content, was_truncated, original_length).
    """
    original_length = len(content)

    if original_length <= max_length:
        return content, False, original_length

    truncated = content[:max_length]

    # Find natural boundary (at least 50% of content preserved)
    for boundary in _PARAGRAPH_BOUNDARIES:
        pos = truncated.rfind(boundary)
        if pos > max_length // 2:
            truncated = truncated[: pos + len(boundary)].rstrip()
            break

    return truncated, True, original_length


class WebFetchTool(BaseAgentTool[WebFetchToolParams]):
    """Tool for fetching content from web pages.

    Uses a FetchProvider to fetch and extract content from URLs.
    Results are cached to avoid redundant fetches.

    Examples:
        ```python
        from openagent.tools.web.providers.fetch import JinaFetchProvider

        provider = JinaFetchProvider()
        tool = WebFetchTool(provider)
        result = await tool(url="https://example.com")
        print(result.output)
        ```
    """

    name: Literal["web_fetch"] = "web_fetch"
    description: str = "Fetch content from a web page."
    args_schema = WebFetchToolParams

    def __init__(self, provider: FetchProvider) -> None:
        """Initialize the WebFetchTool.

        Args:
            provider: The fetch provider to use.
        """
        self._provider = provider

    async def execute(self, params: WebFetchToolParams) -> ToolResult:
        """Fetch content from a URL.

        Args:
            params: Validated parameters containing the URL.

        Returns:
            ToolResult with page content on success, or error on failure.
        """
        # Validate URL
        if error := validate_url(params.url):
            return ToolResult(error=error)

        # Check cache first
        cache = get_fetch_cache()
        key = cache_key(self._provider.name, params.url)

        result = cache.get(key)
        if result is None:
            # Cache miss - fetch from provider
            try:
                result = await self._provider.fetch(params.url)
                cache[key] = result
            except (ConfigurationError, WebAPIError) as exc:
                msg = f"Fetch provider: {exc}"
                raise ToolError(msg) from exc
            except httpx.HTTPError as exc:
                msg = f"Fetch for '{params.url}' failed: {exc}"
                raise ToolError(msg) from exc

        if not result.content:
            return ToolResult(output="Page returned no content.")

        # Check content size limit
        content_size = len(result.content.encode("utf-8"))
        if content_size > MAX_CONTENT_SIZE:
            return ToolResult(error=f"Content exceeds 10MB limit ({content_size:,} bytes)")

        # Apply truncation
        truncated_content, was_truncated, original_length = _truncate_content(result.content)

        # Format output
        lines: list[str] = []
        if result.title:
            lines.append(f"# {result.title}\n")
        lines.append(truncated_content)

        if was_truncated:
            lines.append(f"\n[Content truncated: showing {len(truncated_content):,} of {original_length:,} characters]")

        return ToolResult(output="\n".join(lines))
