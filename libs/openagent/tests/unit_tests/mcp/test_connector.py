# ruff: noqa: PLR2004, TC001
"""Tests for openagent.mcp._connector — McpConnector orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from openagent.mcp._client import McpClient
from openagent.mcp._connector import _MAX_CONNECT_ATTEMPTS, McpConnector
from openagent.mcp._tool import McpTool
from openagent.types import McpServerConfig


def _http_config() -> McpServerConfig:
    return {"type": "http", "url": "https://example.com/mcp"}


def _make_mock_tool(name: str) -> McpTool:
    """Create a minimal McpTool stub for testing aggregation."""
    from pydantic import BaseModel

    class Empty(BaseModel):
        pass

    return McpTool(
        name=name,
        description="stub",
        args_schema=Empty,
        session=AsyncMock(),
        mcp_tool_name=name,
        session_lock=AsyncMock(),
    )


class TestMcpConnectorOrchestration:
    """Test McpConnector as orchestrator over McpClient instances."""

    async def test_enters_and_exits_all_clients(self) -> None:
        enter_calls: list[str] = []
        exit_calls: list[str] = []

        async def mock_aenter(self: McpClient) -> McpClient:
            enter_calls.append(self.name)
            self._exit_stack = AsyncMock()
            return self

        async def mock_aexit(
            self: McpClient,
            _exc_type: object = None,
            _exc_val: object = None,
            _exc_tb: object = None,
        ) -> None:
            exit_calls.append(self.name)
            self._exit_stack = None

        servers = {"s1": _http_config(), "s2": _http_config()}

        with (
            patch.object(McpClient, "__aenter__", mock_aenter),
            patch.object(McpClient, "__aexit__", mock_aexit),
        ):
            async with McpConnector(servers) as connector:
                assert len(connector.clients) == 2
                assert enter_calls == ["s1", "s2"]

        assert exit_calls == ["s2", "s1"]

    async def test_tools_accessible_via_clients(self) -> None:
        """Tools from multiple clients are accessible via client.tools."""

        async def mock_aenter(self: McpClient) -> McpClient:
            self._exit_stack = AsyncMock()
            if self.name == "s1":
                self._tools = [_make_mock_tool("tool_a")]
            else:
                self._tools = [_make_mock_tool("tool_b"), _make_mock_tool("tool_c")]
            return self

        async def mock_aexit(
            self: McpClient,
            _exc_type: object = None,
            _exc_val: object = None,
            _exc_tb: object = None,
        ) -> None:
            self._exit_stack = None
            self._tools = []

        servers = {"s1": _http_config(), "s2": _http_config()}

        with (
            patch.object(McpClient, "__aenter__", mock_aenter),
            patch.object(McpClient, "__aexit__", mock_aexit),
        ):
            async with McpConnector(servers) as connector:
                all_tools = [t for c in connector.clients for t in c.tools]
                assert len(all_tools) == 3
                names = [t.name for t in all_tools]
                assert names == ["tool_a", "tool_b", "tool_c"]

    async def test_clients_property_returns_all(self) -> None:
        async def mock_aenter(self: McpClient) -> McpClient:
            self._exit_stack = AsyncMock()
            return self

        async def mock_aexit(
            self: McpClient,
            _exc_type: object = None,
            _exc_val: object = None,
            _exc_tb: object = None,
        ) -> None:
            self._exit_stack = None

        servers = {"s1": _http_config(), "s2": _http_config()}

        with (
            patch.object(McpClient, "__aenter__", mock_aenter),
            patch.object(McpClient, "__aexit__", mock_aexit),
        ):
            async with McpConnector(servers) as connector:
                clients = connector.clients
                assert len(clients) == 2
                assert all(isinstance(c, McpClient) for c in clients)

    async def test_failure_skips_bad_server_after_retries(self) -> None:
        """If one client fails all retry attempts, connector skips it."""
        attempt_counts: dict[str, int] = {"good": 0, "bad": 0}

        async def mock_aenter(self: McpClient) -> McpClient:
            attempt_counts[self.name] += 1
            if self.name == "bad":
                msg = "connection refused"
                raise ConnectionError(msg)
            self._exit_stack = AsyncMock()
            return self

        async def mock_aexit(
            self: McpClient,
            _exc_type: object = None,
            _exc_val: object = None,
            _exc_tb: object = None,
        ) -> None:
            self._exit_stack = None

        servers = {"good": _http_config(), "bad": _http_config()}

        with (
            patch.object(McpClient, "__aenter__", mock_aenter),
            patch.object(McpClient, "__aexit__", mock_aexit),
            patch("openagent.mcp._connector.asyncio.sleep", new_callable=AsyncMock),
        ):
            async with McpConnector(servers) as connector:
                assert len(connector.clients) == 1
                assert connector.clients[0].name == "good"

        assert attempt_counts["good"] == 1
        assert attempt_counts["bad"] == _MAX_CONNECT_ATTEMPTS

    async def test_retry_succeeds_on_second_attempt(self) -> None:
        """Transient failure on first attempt, success on retry."""
        attempt_count = 0

        async def mock_aenter(self: McpClient) -> McpClient:
            nonlocal attempt_count
            if self.name == "flaky":
                attempt_count += 1
                if attempt_count == 1:
                    msg = "transient error"
                    raise ConnectionError(msg)
            self._exit_stack = AsyncMock()
            return self

        async def mock_aexit(
            self: McpClient,
            _exc_type: object = None,
            _exc_val: object = None,
            _exc_tb: object = None,
        ) -> None:
            self._exit_stack = None

        servers = {"flaky": _http_config()}

        with (
            patch.object(McpClient, "__aenter__", mock_aenter),
            patch.object(McpClient, "__aexit__", mock_aexit),
            patch("openagent.mcp._connector.asyncio.sleep", new_callable=AsyncMock),
        ):
            async with McpConnector(servers) as connector:
                assert len(connector.clients) == 1
                assert connector.clients[0].name == "flaky"

        assert attempt_count == 2

    async def test_repr(self) -> None:
        servers = {"s1": _http_config(), "s2": _http_config()}
        connector = McpConnector(servers)
        result = repr(connector)
        assert "McpConnector" in result
        assert "s1" in result
        assert "s2" in result
