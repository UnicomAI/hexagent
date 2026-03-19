"""Adapter for converting OpenAgent tools to LangChain tools.

This module provides the bridge between OpenAgent's framework-agnostic
BaseAgentTool and LangChain's StructuredTool interface.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool

if TYPE_CHECKING:
    from openagent.tools.base import BaseAgentTool

# Return type for content_and_artifact response format:
# (content, artifact) where content is a list of content blocks.
_ContentAndArtifact = tuple[list[dict[str, Any]], None]


def to_langchain_tool(tool: BaseAgentTool[Any]) -> StructuredTool:
    """Convert a BaseAgentTool to a LangChain StructuredTool.

    Creates a thin wrapper that adapts the BaseAgentTool interface to
    LangChain's StructuredTool interface. Uses ``response_format=
    "content_and_artifact"`` so that multimodal results (images) are
    preserved as structured content blocks in the ``ToolMessage``.

    Args:
        tool: The agent tool to convert.

    Returns:
        A LangChain StructuredTool wrapping the agent tool.

    Examples:
        ```python
        from openagent.tools.cli import BashTool
        from openagent.langchain import to_langchain_tool

        bash_tool = BashTool(computer)
        langchain_tool = to_langchain_tool(bash_tool)

        # Schema is derived from tool.args_schema
        print(langchain_tool.args_schema)  # BashToolParams

        # Now usable in LangChain agents
        result = await langchain_tool.ainvoke({"command": "echo hello"})
        ```
    """

    async def async_invoke(**kwargs: Any) -> _ContentAndArtifact:
        """Async invocation with result conversion."""
        result = await tool(**kwargs)
        return result.to_content_blocks("anthropic"), None

    def sync_invoke(**kwargs: Any) -> _ContentAndArtifact:
        """Sync wrapper for async invocation.

        Required because LangGraph's tool node may invoke tools synchronously.
        """
        import asyncio

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(async_invoke(**kwargs))
        else:
            # Already in an async context - create a new event loop in a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, async_invoke(**kwargs))
                return future.result()

    return StructuredTool.from_function(
        name=tool.name,
        description=tool.description,
        func=sync_invoke,
        coroutine=async_invoke,
        args_schema=tool.json_schema,
        response_format="content_and_artifact",
    )
