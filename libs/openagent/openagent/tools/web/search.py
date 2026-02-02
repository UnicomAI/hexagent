"""Web search tool for searching the internet.

Provides WebSearchTool for agents to search the web.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

import httpx

from openagent.exceptions import ConfigurationError, ToolError, WebAPIError
from openagent.tools.base import BaseAgentTool
from openagent.tools.web._cache import cache_key, get_search_cache
from openagent.types import ToolResult, WebSearchToolParams

if TYPE_CHECKING:
    from openagent.tools.web.providers.search import SearchProvider

MAX_SEARCH_RESULTS = 10


class WebSearchTool(BaseAgentTool[WebSearchToolParams]):
    """Tool for searching the web.

    Uses a SearchProvider to perform web searches.
    Results are cached to avoid redundant searches.

    Examples:
        ```python
        from openagent.tools.web.providers.search import TavilySearchProvider

        provider = TavilySearchProvider()
        tool = WebSearchTool(provider)
        result = await tool(query="python async programming")
        print(result.output)
        ```
    """

    name: Literal["web_search"] = "web_search"
    description: str = "Search the web for information."
    args_schema = WebSearchToolParams

    def __init__(self, provider: SearchProvider) -> None:
        """Initialize the WebSearchTool.

        Args:
            provider: The search provider to use.
        """
        self._provider = provider

    async def execute(self, params: WebSearchToolParams) -> ToolResult:
        """Execute a web search.

        Args:
            params: Validated parameters containing the query.

        Returns:
            ToolResult with formatted search results.
        """
        # Check cache first
        cache = get_search_cache()
        key = cache_key(self._provider.name, params.query, str(MAX_SEARCH_RESULTS))

        result = cache.get(key)
        if result is None:
            # Cache miss - search
            try:
                result = await self._provider.search(
                    params.query,
                    max_results=MAX_SEARCH_RESULTS,
                )
                cache[key] = result
            except (ConfigurationError, WebAPIError) as exc:
                msg = f"Search provider: {exc}"
                raise ToolError(msg) from exc
            except httpx.HTTPError as exc:
                msg = f"Search for '{params.query}' failed: {exc}"
                raise ToolError(msg) from exc

        if not result.items:
            return ToolResult(output=f'No results found for query: "{params.query}".')

        # Format results differently based on AI summary availability
        if result.ai_summary:
            # Compact format with AI summary
            links = [{"title": item.title, "url": item.url} for item in result.items]
            output = "\n\n".join(
                [
                    f'Web search results for query: "{params.query}"',
                    f"Links: {json.dumps(links)}",
                    result.ai_summary,
                ]
            )
        else:
            # Detailed format with snippets
            blocks: list[str] = []
            for item in result.items:
                block = f"Title: {item.title}\nURL: {item.url}\n\n{item.snippet}"
                blocks.append(block)
            output = "\n\n---\n\n".join(blocks)

        return ToolResult(output=output)
