"""MCP (Model Context Protocol) connector for OpenAgent.

Connects to remote MCP servers, discovers their tools, and integrates
them into the OpenAgent tool pipeline.

Usage::

    from openagent import create_agent

    async with await create_agent(
        model,
        computer,
        mcp_servers={
            "my-server": {"type": "http", "url": "https://mcp.example.com/mcp"},
        },
    ) as agent:
        result = await agent.ainvoke({"messages": [...]})
"""

from openagent.mcp._client import McpClient
from openagent.mcp._tool import McpTool

__all__ = [
    "McpClient",
    "McpTool",
]
