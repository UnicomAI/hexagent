"""McpTool — BaseAgentTool subclass wrapping a remote MCP tool.

Each instance wraps a single tool discovered from an MCP server.
Instances are created by :class:`McpConnector` during tool discovery
and are only valid while the connector's async context is active.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from hexagent.tools.base import BaseAgentTool
from hexagent.types import Base64Source, ImageContent, ToolResult

if TYPE_CHECKING:
    import asyncio

    from mcp import ClientSession
    from mcp.types import CallToolResult


class McpTool(BaseAgentTool[BaseModel]):
    """A dynamically constructed tool wrapping an MCP server tool call.

    Attributes:
        name: Prefixed tool name (``mcp__<server>__<tool>``).
        description: Human-readable description from the MCP server.
        args_schema: Dynamically generated Pydantic model from the MCP
            tool's ``inputSchema``.
    """

    name: str
    description: str
    args_schema: type[BaseModel]

    def __init__(
        self,
        *,
        name: str,
        description: str,
        args_schema: type[BaseModel],
        session: ClientSession,
        mcp_tool_name: str,
        session_lock: asyncio.Lock,
    ) -> None:
        self.name = name
        self.description = description
        self.args_schema = args_schema
        self._session = session
        self._mcp_tool_name = mcp_tool_name
        self._session_lock = session_lock

    def __repr__(self) -> str:
        """Return a string representation of the tool."""
        max_desc_len = 80
        desc = self.description[:max_desc_len] + "…" if len(self.description) > max_desc_len else self.description
        return f"McpTool(name={self.name!r}, description={desc!r})"

    async def execute(self, params: BaseModel) -> ToolResult:
        """Execute the MCP tool call and convert the result.

        Args:
            params: Validated parameters matching ``args_schema``.

        Returns:
            ToolResult with output, error, or image content.
        """
        arguments = params.model_dump(exclude_unset=True)
        async with self._session_lock:
            result = await self._session.call_tool(self._mcp_tool_name, arguments)
        return _convert_result(result)


def _convert_result(result: CallToolResult) -> ToolResult:
    """Convert an MCP CallToolResult to an HexAgent ToolResult.

    Args:
        result: The CallToolResult from ``session.call_tool()``.

    Returns:
        A ToolResult with appropriate output/error/images fields.
    """
    text_parts: list[str] = []
    images: list[ImageContent] = []

    for block in result.content:
        block_type: Any = getattr(block, "type", None)
        if block_type == "text":
            text_parts.append(block.text)  # type: ignore[union-attr]
        elif block_type == "image":
            images.append(
                Base64Source(
                    data=block.data,  # type: ignore[union-attr]
                    media_type=getattr(block, "mimeType", "image/png"),
                )
            )

    if result.isError:
        error_msg = "\n".join(text_parts) if text_parts else "MCP tool returned an error"
        return ToolResult(error=error_msg)

    output = "\n".join(text_parts) if text_parts else None

    if output is None and result.structuredContent:
        output = json.dumps(result.structuredContent)

    return ToolResult(output=output, images=tuple(images))
