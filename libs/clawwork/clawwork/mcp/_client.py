"""McpClient — per-server live connection to a single MCP server.

Owns the transport, session, and discovered tools for one MCP server.
Instances are created and managed by :class:`McpConnector`.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Any, Self, cast

import httpx
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import PaginatedRequestParams, Tool

from clawwork.mcp._schema import json_schema_to_model
from clawwork.mcp._tool import McpTool

if TYPE_CHECKING:
    from types import TracebackType

    from pydantic import BaseModel

    from clawwork.types import McpHttpServerConfig, McpServerConfig, McpSseServerConfig, McpStdioServerConfig

logger = logging.getLogger(__name__)

# Default timeout for each phase of the MCP connection handshake.
# Generous enough for cold-start servers behind proxies, tight enough
# to avoid blocking agent creation on a dead endpoint.
_DEFAULT_TRANSPORT_TIMEOUT_S: float = 30.0
_DEFAULT_SESSION_INIT_TIMEOUT_S: float = 15.0
_DEFAULT_LIST_TOOLS_TIMEOUT_S: float = 15.0


def _to_pascal_case(s: str) -> str:
    """Convert a snake_case or separator-delimited string to PascalCase."""
    return "".join(part.capitalize() for part in s.replace("-", "_").split("_") if part)


class McpClient:
    """A live connection to a single MCP server.

    Use as an async context manager. Once entered, discovered tools
    are available via :attr:`tools` and server instructions via
    :attr:`instructions`.
    """

    def __init__(self, name: str, config: McpServerConfig) -> None:
        self._name = name
        self._config = config
        self._instructions: str = ""
        self._tools: list[McpTool] = []
        self._exit_stack: AsyncExitStack | None = None

    # --- Properties ---

    @property
    def name(self) -> str:
        """Human-readable server identifier (the dict key)."""
        return self._name

    @property
    def config(self) -> McpServerConfig:
        """The server configuration used to create this client."""
        return self._config

    @property
    def instructions(self) -> str:
        """Server-provided instructions from MCP ``initialize()``, or ``""``."""
        return self._instructions

    @property
    def tools(self) -> list[McpTool]:
        """Discovered MCP tools (populated after ``__aenter__``)."""
        return list(self._tools)

    @property
    def is_connected(self) -> bool:
        """Whether the server connection is active."""
        return self._exit_stack is not None

    # --- Repr ---

    def __repr__(self) -> str:
        """Return a string representation of the client."""
        return f"McpClient(name={self._name!r}, tools={self._tools!r}, connected={self.is_connected})"

    # --- Async context manager ---

    async def __aenter__(self) -> Self:
        """Enter the async context manager and connect to the MCP server."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        try:
            await self._connect()
        except BaseException:
            await self._exit_stack.__aexit__(None, None, None)
            self._exit_stack = None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and disconnect."""
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            self._exit_stack = None
            self._tools = []
            self._instructions = ""

    # --- Connection logic ---

    async def _connect(self) -> None:
        """Open transport, create session, discover tools.

        Each phase has an independent timeout so a slow server cannot
        block agent creation indefinitely.
        """
        assert self._exit_stack is not None  # noqa: S101
        session = await self._open_session()

        async with asyncio.timeout(_DEFAULT_LIST_TOOLS_TIMEOUT_S):
            mcp_tools = await _list_all_tools(session)

        lock = asyncio.Lock()
        self._tools = [_create_mcp_tool(self._name, t, session, lock) for t in mcp_tools]
        logger.info(
            "Connected to MCP server '%s' — discovered %d tool(s)",
            self.name,
            len(self._tools),
        )

    async def _open_session(self) -> ClientSession:
        """Open transport and create an initialized MCP ClientSession."""
        assert self._exit_stack is not None  # noqa: S101

        async with asyncio.timeout(_DEFAULT_TRANSPORT_TIMEOUT_S):
            read_stream, write_stream = await self._open_transport()

        session: ClientSession = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream),
        )

        async with asyncio.timeout(_DEFAULT_SESSION_INIT_TIMEOUT_S):
            result = await session.initialize()

        self._instructions = result.instructions or ""
        return session

    async def _open_transport(self) -> tuple[Any, Any]:
        """Open the appropriate transport and return (read_stream, write_stream)."""
        assert self._exit_stack is not None  # noqa: S101
        config = self._config
        transport_type = config["type"]

        if transport_type == "http":
            http_cfg = cast("McpHttpServerConfig", config)
            http_client = await self._exit_stack.enter_async_context(
                httpx.AsyncClient(headers=dict(http_cfg.get("headers", {}))),
            )
            read_stream, write_stream, _ = await self._exit_stack.enter_async_context(
                streamable_http_client(http_cfg["url"], http_client=http_client),
            )
        elif transport_type == "sse":
            sse_cfg = cast("McpSseServerConfig", config)
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                sse_client(sse_cfg["url"], headers=dict(sse_cfg.get("headers", {}))),
            )
        else:  # stdio (default)
            stdio_cfg = cast("McpStdioServerConfig", config)
            server_params = StdioServerParameters(
                command=stdio_cfg["command"],
                args=list(stdio_cfg.get("args", [])),
                env=stdio_cfg.get("env"),
            )
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(server_params),
            )

        return read_stream, write_stream


async def _list_all_tools(session: ClientSession) -> list[Tool]:
    """Collect all tools from an MCP server, handling pagination."""
    all_tools: list[Tool] = []
    cursor: str | None = None

    while True:
        params = PaginatedRequestParams(cursor=cursor) if cursor else None
        result = await session.list_tools(params=params)
        all_tools.extend(result.tools)
        cursor = getattr(result, "nextCursor", None)
        if cursor is None:
            break

    return all_tools


def _create_mcp_tool(
    server_name: str,
    mcp_tool: Tool,
    session: ClientSession,
    lock: asyncio.Lock,
) -> McpTool:
    """Create a single McpTool from an MCP Tool descriptor."""
    tool_name = f"mcp__{server_name}__{mcp_tool.name}"
    description = mcp_tool.description or mcp_tool.title or f"Tool from MCP server '{server_name}'"

    args_schema: type[BaseModel] = json_schema_to_model(
        _to_pascal_case(tool_name),
        mcp_tool.inputSchema,
    )

    return McpTool(
        name=tool_name,
        description=description,
        args_schema=args_schema,
        session=session,
        mcp_tool_name=mcp_tool.name,
        session_lock=lock,
    )
