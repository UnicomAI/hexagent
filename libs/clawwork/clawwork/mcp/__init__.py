"""MCP (Model Context Protocol) connector for ClawWork.

Connects to remote MCP servers, discovers their tools, and integrates
them into the ClawWork tool pipeline.

Usage::

    from clawwork import create_agent

    async with await create_agent(
        model,
        computer,
        mcp_servers={
            "my-server": {"type": "http", "url": "https://mcp.example.com/mcp"},
        },
    ) as agent:
        result = await agent.ainvoke({"messages": [...]})
"""

from clawwork.mcp._client import McpClient
from clawwork.mcp._tool import McpTool

__all__ = [
    "McpClient",
    "McpTool",
]
