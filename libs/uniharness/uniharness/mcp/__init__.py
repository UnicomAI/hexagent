"""MCP (Model Context Protocol) connector for UniHarness.

Connects to remote MCP servers, discovers their tools, and integrates
them into the UniHarness tool pipeline.

Usage::

    from uniharness import create_agent

    async with await create_agent(
        model,
        computer,
        mcp_servers={
            "my-server": {"type": "http", "url": "https://mcp.example.com/mcp"},
        },
    ) as agent:
        result = await agent.ainvoke({"messages": [...]})
"""

from uniharness.mcp._client import McpClient
from uniharness.mcp._tool import McpTool

__all__ = [
    "McpClient",
    "McpTool",
]
