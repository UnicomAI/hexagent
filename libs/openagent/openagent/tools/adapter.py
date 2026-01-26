"""Adapter utilities for converting agent tools to different frameworks.

This module provides adapter functions to convert OpenAgent's BaseAgentTool
to other tool interfaces like LangChain's BaseTool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from langchain_core.tools import StructuredTool

if TYPE_CHECKING:
    from openagent.tools.base import BaseAgentTool


def to_langchain_tool(tool: BaseAgentTool[Any]) -> StructuredTool:
    """Convert a BaseAgentTool to a LangChain StructuredTool.

    Creates a thin wrapper that adapts the BaseAgentTool interface to
    LangChain's StructuredTool interface. Async-only - no sync wrapper.

    The adapter derives all metadata (name, description, schema) from
    the OpenAgent tool, ensuring single source of truth.

    Args:
        tool: The agent tool to convert.

    Returns:
        A LangChain StructuredTool wrapping the agent tool.

    Examples:
        ```python
        from openagent.tools.computer import BashTool
        from openagent.tools.adapter import to_langchain_tool

        bash_tool = BashTool(computer)
        langchain_tool = to_langchain_tool(bash_tool)

        # Schema is derived from tool.args_schema
        print(langchain_tool.args_schema)  # BashToolParams

        # Now usable in LangChain agents
        result = await langchain_tool.ainvoke({"command": "echo hello"})
        ```
    """

    async def async_invoke(**kwargs: Any) -> str:
        """Async invocation with result conversion."""
        result = await tool(**kwargs)
        return result.to_text()

    def sync_invoke(**kwargs: Any) -> str:
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
        args_schema=tool.args_schema,
    )
