"""McpConnector — orchestrates connections to multiple MCP servers.

Thin orchestrator over :class:`McpClient` instances. Opens all clients
on entry and tears them down on exit.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Self

from openagent.mcp._client import McpClient

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType

    from openagent.mcp._tool import McpTool
    from openagent.types import McpServerConfig


class McpConnector:
    """Orchestrates connections to multiple MCP servers.

    Use as an async context manager. All servers are connected on entry
    and disconnected on exit.
    """

    def __init__(self, servers: Mapping[str, McpServerConfig]) -> None:
        self._clients = [McpClient(name, config) for name, config in servers.items()]
        self._exit_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> Self:
        """Connect to all MCP servers."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        try:
            for client in self._clients:
                await self._exit_stack.enter_async_context(client)
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
        """Disconnect from all MCP servers."""
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)
            self._exit_stack = None

    @property
    def tools(self) -> list[McpTool]:
        """Aggregated tools from all connected servers."""
        return [t for c in self._clients for t in c.tools]

    @property
    def clients(self) -> list[McpClient]:
        """Connected McpClient instances."""
        return list(self._clients)

    def __repr__(self) -> str:
        """Return a string representation of the connector."""
        return f"McpConnector({self._clients})"
