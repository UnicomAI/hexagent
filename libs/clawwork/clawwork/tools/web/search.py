"""Web search tool for searching the internet.

Provides WebSearchTool for agents to search the web.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

import httpx

from clawwork.exceptions import ConfigurationError, ToolError, WebAPIError
from clawwork.prompts.content import load, substitute
from clawwork.tools.base import BaseAgentTool
from clawwork.tools.web._cache import cache_key, get_search_cache
from clawwork.types import ToolResult, WebSearchToolParams

if TYPE_CHECKING:
    from clawwork.tools.web.providers.search import SearchProvider
    from clawwork.types import CompletionModel

MAX_SEARCH_RESULTS = 10


class WebSearchTool(BaseAgentTool[WebSearchToolParams]):
    """Tool for searching the web.

    Uses a SearchProvider to perform web searches.
    Results are cached to avoid redundant searches.

    Examples:
        ```python
        from clawwork.tools.web.providers.search import TavilySearchProvider

        provider = TavilySearchProvider()
        tool = WebSearchTool(provider)
        result = await tool(query="python async programming")
        print(result.output)
        ```
    """

    name: Literal["WebSearch"] = "WebSearch"
    description: str = "Search the web for information."
    args_schema = WebSearchToolParams

    def __init__(
        self,
        provider: SearchProvider,
        *,
        model: CompletionModel | None = None,
    ) -> None:
        """Initialize the WebSearchTool.

        Args:
            provider: The search provider to use.
            model: Optional LLM for generating an AI summary when the
                provider does not return one.
        """
        self._provider = provider
        self._model = model

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

        # Resolve AI summary: use provider's if available, else generate one.
        ai_summary = result.ai_summary
        if not ai_summary and self._model:
            formatted_results = "\n\n".join(
                f"[{i}] {item.title}" + (f"\nDate: {item.date.strftime('%-d %b %Y')}" if item.date else "") + f"\nURL: {item.url}\n{item.snippet}"
                for i, item in enumerate(result.items, 1)
            )
            user_msg = substitute(
                load("agent_prompt_websearch_summarizer"),
                FORMATTED_SEARCH_RESULTS=formatted_results,
                SEARCH_QUERY=params.query,
            )
            ai_summary = await self._model.complete(
                system=(
                    "You are a search result synthesizer. Produce a direct, accurate"
                    " answer by combining information across the provided search results."
                    " Include all key facts, figures, dates, and named entities that are"
                    " relevant to the query. When results conflict, note the discrepancy."
                    " Prefer the most recent information when timeliness matters. Never"
                    " fabricate information beyond what the results contain."
                ),
                user=user_msg,
            )

        # Format output based on summary availability
        if ai_summary:
            links = [{"title": item.title, "url": item.url} for item in result.items]
            output = "\n\n".join(
                [
                    f'Web search results for query: "{params.query}"',
                    f"Links: {json.dumps(links, ensure_ascii=False)}",
                    ai_summary,
                ]
            )
        else:
            # Detailed format with snippets (no model, no provider summary)
            blocks: list[str] = []
            for item in result.items:
                block = f"Title: {item.title}\nURL: {item.url}\n\n{item.snippet}"
                blocks.append(block)
            output = "\n\n---\n\n".join(blocks)

        output += "\n\n[REMINDER: You MUST include the sources above in your response to the user using markdown hyperlinks.]"
        return ToolResult(output=output)
