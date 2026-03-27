"""MCP (Model Context Protocol) connector for HexAgent.

Connects to remote MCP servers, discovers their tools, and integrates
them into the HexAgent tool pipeline.

Usage::

    from hexagent import create_agent

    async with await create_agent(
        model,
        computer,
        mcp_servers={
            "my-server": {"type": "http", "url": "https://mcp.example.com/mcp"},
        },
    ) as agent:
        result = await agent.ainvoke({"messages": [...]})
"""

from hexagent.mcp._client import McpClient
from hexagent.mcp._tool import McpTool

__all__ = [
    "McpClient",
    "McpTool",
]
