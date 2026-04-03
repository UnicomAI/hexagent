"""Web search tool for searching the internet.

Provides WebSearchTool for agents to search the web.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Literal

import httpx

from hexagent.exceptions import ConfigurationError, ToolError, WebAPIError
from hexagent.prompts.content import load, substitute
from hexagent.tools.base import BaseAgentTool
from hexagent.tools.web._cache import cache_key, get_search_cache
from hexagent.types import ToolResult, WebSearchToolParams

if TYPE_CHECKING:
    from hexagent.tools.web.providers.search import SearchProvider
    from hexagent.types import CompletionModel

MAX_SEARCH_RESULTS = 10


class WebSearchTool(BaseAgentTool[WebSearchToolParams]):
    """Tool for searching the web.

    Uses a SearchProvider to perform web searches.
    Results are cached to avoid redundant searches.

    Examples:
        ```python
        from hexagent.tools.web.providers.search import TavilySearchProvider

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
        logger = logging.getLogger(__name__)
        logger.info(f"Executing WebSearch for query: '{params.query}' using provider: {self._provider.name}")
        
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
                logger.debug(f"Search provider returned {len(result.items)} items")
                cache[key] = result
            except (ConfigurationError, WebAPIError) as exc:
                msg = f"Search provider: {exc}"
                logger.error(f"Search provider error: {msg}")
                return ToolResult(error=msg)
            except httpx.HTTPError as exc:
                msg = f"Search for '{params.query}' failed: {exc}"
                logger.error(f"HTTP error during search: {msg}")
                return ToolResult(error=msg)
            except Exception as exc:
                msg = f"An unexpected error occurred while searching for '{params.query}': {exc}"
                logger.exception(f"Unexpected error during search: {msg}")
                return ToolResult(error=msg)

        if not result.items:
            logger.info(f"No search results found for query: '{params.query}'")
            return ToolResult(output=f'No results found for query: "{params.query}".')

        # Resolve AI summary: use provider's if available, else generate one.
        ai_summary = result.ai_summary
        if not ai_summary and self._model:
            logger.info("No provider summary, generating AI summary using model...")
            try:
                formatted_results = "\n\n".join(
                    f"[{i}] {item.title}" + (f"\nDate: {item.date.strftime('%d %b %Y')}" if item.date else "") + f"\nURL: {item.url}\n{item.snippet}"
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
                logger.debug("AI summary generated successfully")
            except Exception as exc:
                logger.exception(f"Error generating AI summary: {exc}")
                # Fallback to no summary if generation fails
                ai_summary = None

        # Format output based on summary availability
        if ai_summary:
            links = []
            for item in result.items:
                link_info = {"title": item.title, "url": item.url}
                if item.image_url:
                    link_info["image_url"] = item.image_url
                if item.image_title:
                    link_info["image_title"] = item.image_title
                links.append(link_info)
                
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
                block = f"Title: {item.title}\nURL: {item.url}"
                if item.image_url:
                    if item.image_title:
                        block += f"\nImage: {item.image_title} ({item.image_url})"
                    else:
                        block += f"\nImage: {item.image_url}"
                block += f"\n\n{item.snippet}"
                blocks.append(block)
            output = "\n\n---\n\n".join(blocks)

        output += "\n\n[REMINDER: You MUST include the sources above in your response to the user using markdown hyperlinks.]"
        return ToolResult(output=output)
