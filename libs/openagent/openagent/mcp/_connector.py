"""McpConnector — orchestrates connections to multiple MCP servers.

Thin orchestrator over :class:`McpClient` instances. Opens all clients
on entry and tears them down on exit.  Individual connection failures
are logged and skipped so one broken server never blocks the agent.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Self

from openagent.mcp._client import McpClient

if TYPE_CHECKING:
    from collections.abc import Mapping
    from types import TracebackType

    from openagent.types import McpServerConfig

logger = logging.getLogger(__name__)

# Retry policy for transient MCP connection failures.
_MAX_CONNECT_ATTEMPTS: int = 3
_RETRY_BACKOFF_S: tuple[float, ...] = (1.0, 3.0)


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
        """Connect to all MCP servers, skipping any that fail.

        Each server is retried up to ``_MAX_CONNECT_ATTEMPTS`` times with
        exponential backoff for transient errors (broken transport, timeout,
        network blip).  After exhausting retries the server is skipped and
        the remaining servers continue connecting.
        """
        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()
        for client in self._clients:
            connected = await self._connect_with_retry(client)
            if connected:
                self._connected.append(client)
        return self

    async def _connect_with_retry(self, client: McpClient) -> bool:
        """Try to connect a single client, retrying on transient failures.

        Returns ``True`` if the client connected successfully.
        """
        assert self._exit_stack is not None  # noqa: S101
        last_exc: Exception | None = None

        for attempt in range(_MAX_CONNECT_ATTEMPTS):
            try:
                await self._exit_stack.enter_async_context(client)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < _MAX_CONNECT_ATTEMPTS - 1:
                    delay = _RETRY_BACKOFF_S[min(attempt, len(_RETRY_BACKOFF_S) - 1)]
                    logger.warning(
                        "MCP server '%s' connection attempt %d/%d failed (%s: %s), retrying in %.1fs…",
                        client.name,
                        attempt + 1,
                        _MAX_CONNECT_ATTEMPTS,
                        type(exc).__name__,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    # Re-create the client so it gets a fresh exit stack
                    # (the previous __aenter__ already cleaned up on failure).
                    client = McpClient(client.name, client.config)
            else:
                return True

        logger.warning(
            "Failed to connect to MCP server '%s' after %d attempts, skipping.",
            client.name,
            _MAX_CONNECT_ATTEMPTS,
            exc_info=last_exc,
        )
        return False

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
