"""McpConnector — orchestrates connections to multiple MCP servers.

Thin orchestrator over :class:`McpClient` instances. Opens all clients
on entry and tears them down on exit.  Individual connection failures
are logged and skipped so one broken server never blocks the agent.
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Self

from openagent.mcp._client import McpClient

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType

    from openagent.types import McpServerConfig

logger = logging.getLogger(__name__)


class McpConnector:
    """Orchestrates connections to multiple MCP servers.

    Use as an async context manager. All servers are connected on entry
    and disconnected on exit.  Servers that fail to connect are skipped
    with a warning — they do not prevent the remaining servers from
    connecting.
    """

    def __init__(self, servers: Mapping[str, McpServerConfig]) -> None:
        self._clients = [McpClient(name, config) for name, config in servers.items()]
        self._connected: list[McpClient] = []
        self._exit_stack: AsyncExitStack | None = None

    async def __aenter__(self) -> Self:
        """Connect to all MCP servers, skipping any that fail."""
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        for client in self._clients:
            try:
                await self._exit_stack.enter_async_context(client)
                self._connected.append(client)
            except (OSError, RuntimeError, ValueError, BaseExceptionGroup):
                logger.warning(
                    "Failed to connect to MCP server '%s', skipping.",
                    client.name,
                    exc_info=True,
                )
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
            self._connected.clear()

    @property
    def clients(self) -> list[McpClient]:
        """Successfully connected McpClient instances."""
        return list(self._connected)

    def __repr__(self) -> str:
        """Return a string representation of the connector."""
        names = [c.name for c in self._clients]
        return f"McpConnector(servers={names!r})"
