# ruff: noqa: PLR2004, TC001, TC003
"""Tests for hexagent.mcp._client — McpClient lifecycle and transport."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import mcp.types as mcp_types
import pytest

from hexagent.mcp._client import McpClient, _create_mcp_tool, _list_all_tools
from hexagent.types import McpServerConfig


def _make_mcp_tool(
    name: str = "my_tool",
    description: str = "A test tool",
    input_schema: dict[str, Any] | None = None,
) -> mcp_types.Tool:
    return mcp_types.Tool(
        name=name,
        description=description,
        inputSchema=input_schema or {"type": "object", "properties": {}},
    )


def _make_list_tools_result(
    tools: list[mcp_types.Tool],
    next_cursor: str | None = None,
) -> mcp_types.ListToolsResult:
    return mcp_types.ListToolsResult(tools=tools, nextCursor=next_cursor)


def _make_mock_session(
    tools: list[mcp_types.Tool] | None = None,
    instructions: str | None = None,
) -> AsyncMock:
    """Build a mock ClientSession with configurable initialize result."""
    session = AsyncMock()
    init_result = MagicMock()
    init_result.instructions = instructions
    session.initialize = AsyncMock(return_value=init_result)
    session.list_tools = AsyncMock(
        return_value=_make_list_tools_result(tools or []),
    )
    return session


def _http_config() -> McpServerConfig:
    return {"type": "http", "url": "https://example.com/mcp"}


def _sse_config() -> McpServerConfig:
    return {"type": "sse", "url": "https://example.com/sse"}


def _stdio_config() -> McpServerConfig:
    return {"type": "stdio", "command": "npx", "args": ["-y", "my-mcp-server"]}


class TestMcpClientLifecycle:
    """Test context manager lifecycle."""

    async def test_enters_and_exits_cleanly(self) -> None:
        tools = [_make_mcp_tool()]
        session = _make_mock_session(tools)

        client = McpClient("test-server", _http_config())
        with patch.object(McpClient, "_open_session", return_value=session):
            async with client:
                assert len(client.tools) == 1
                assert client.is_connected

        assert not client.is_connected
        assert client.tools == []

    async def test_tools_empty_when_no_tools(self) -> None:
        session = _make_mock_session([])

        client = McpClient("test-server", _http_config())
        with patch.object(McpClient, "_open_session", return_value=session):
            async with client:
                assert client.tools == []

    async def test_is_connected_property(self) -> None:
        session = _make_mock_session([])

        client = McpClient("test-server", _http_config())
        assert not client.is_connected
        with patch.object(McpClient, "_open_session", return_value=session):
            async with client:
                assert client.is_connected
        assert not client.is_connected

    async def test_repr_connected(self) -> None:
        session = _make_mock_session([_make_mcp_tool()])

        client = McpClient("test-server", _http_config())
        with patch.object(McpClient, "_open_session", return_value=session):
            async with client:
                r = repr(client)
                assert r.startswith("McpClient(name='test-server', tools=[McpTool(")
                assert r.endswith("], connected=True)")

    async def test_repr_disconnected(self) -> None:
        client = McpClient("test-server", _http_config())
        assert repr(client) == "McpClient(name='test-server', tools=[], connected=False)"

    async def test_name_property(self) -> None:
        client = McpClient("my-server", _http_config())
        assert client.name == "my-server"

    async def test_instructions_empty_by_default(self) -> None:
        client = McpClient("test-server", _http_config())
        assert client.instructions == ""


class TestInstructionsCapture:
    """Test that instructions from MCP initialize() are captured."""

    async def test_instructions_populated_from_initialize(self) -> None:
        session = _make_mock_session(instructions="Use this server for GitHub operations.")

        client = McpClient("github", _http_config())
        with patch.object(McpClient, "_open_session", return_value=session):
            # Manually set instructions as _open_session would
            client._instructions = "Use this server for GitHub operations."
            async with client:
                pass

        # Test via the actual _open_session flow
        client2 = McpClient("github", _http_config())
        client2._exit_stack = AsyncExitStack()
        await client2._exit_stack.__aenter__()
        try:
            with patch("hexagent.mcp._client.McpClient._open_transport", return_value=(AsyncMock(), AsyncMock())):
                mock_session = AsyncMock()
                init_result = MagicMock()
                init_result.instructions = "Server instructions here"
                mock_session.initialize = AsyncMock(return_value=init_result)

                with patch("hexagent.mcp._client.ClientSession", return_value=mock_session):
                    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                    mock_session.__aexit__ = AsyncMock(return_value=None)
                    await client2._open_session()
                    assert client2.instructions == "Server instructions here"
        finally:
            await client2._exit_stack.__aexit__(None, None, None)

    async def test_instructions_default_to_empty_when_none(self) -> None:
        session = _make_mock_session(instructions=None)

        client = McpClient("test", _http_config())
        with patch.object(McpClient, "_open_session", return_value=session):
            async with client:
                pass
        # After disconnect, instructions reset
        assert client.instructions == ""

    async def test_instructions_reset_on_exit(self) -> None:
        client = McpClient("test", _http_config())
        client._instructions = "some instructions"
        client._exit_stack = AsyncExitStack()
        await client._exit_stack.__aenter__()
        await client.__aexit__(None, None, None)
        assert client.instructions == ""


class TestTransportDispatch:
    """Test transport type routing via _open_transport."""

    @asynccontextmanager
    async def _mock_streamable_http(
        self,
        url: str,
        *,
        http_client: object = None,
    ) -> AsyncIterator[tuple[AsyncMock, AsyncMock, MagicMock]]:
        yield (AsyncMock(), AsyncMock(), MagicMock())

    @asynccontextmanager
    async def _mock_sse(
        self,
        url: str,
        headers: object = None,
    ) -> AsyncIterator[tuple[AsyncMock, AsyncMock]]:
        yield (AsyncMock(), AsyncMock())

    @asynccontextmanager
    async def _mock_stdio(
        self,
        server_params: object,
    ) -> AsyncIterator[tuple[AsyncMock, AsyncMock]]:
        yield (AsyncMock(), AsyncMock())

    async def test_http_transport(self) -> None:
        client = McpClient("test", _http_config())
        client._exit_stack = AsyncExitStack()
        await client._exit_stack.__aenter__()

        try:
            with patch(
                "hexagent.mcp._client.streamable_http_client",
                self._mock_streamable_http,
            ):
                read, write = await client._open_transport()
                assert read is not None
                assert write is not None
        finally:
            await client._exit_stack.__aexit__(None, None, None)

    async def test_sse_transport(self) -> None:
        client = McpClient("test", _sse_config())
        client._exit_stack = AsyncExitStack()
        await client._exit_stack.__aenter__()

        try:
            with patch("hexagent.mcp._client.sse_client", self._mock_sse):
                read, write = await client._open_transport()
                assert read is not None
                assert write is not None
        finally:
            await client._exit_stack.__aexit__(None, None, None)

    async def test_stdio_transport(self) -> None:
        client = McpClient("test", _stdio_config())
        client._exit_stack = AsyncExitStack()
        await client._exit_stack.__aenter__()

        try:
            with patch("hexagent.mcp._client.stdio_client", self._mock_stdio):
                read, write = await client._open_transport()
                assert read is not None
                assert write is not None
        finally:
            await client._exit_stack.__aexit__(None, None, None)


class TestToolNaming:
    """Test tool name generation and attributes."""

    def test_tool_name_format(self) -> None:
        lock = asyncio.Lock()
        mcp_tool = _make_mcp_tool(name="create_issue", description="Create a GitHub issue")

        tool = _create_mcp_tool("github", mcp_tool, AsyncMock(), lock)

        assert tool.name == "mcp__github__create_issue"
        assert tool.description == "Create a GitHub issue"

    def test_description_fallback_to_title(self) -> None:
        lock = asyncio.Lock()
        mcp_tool = mcp_types.Tool(
            name="my_tool",
            title="My Tool Title",
            description=None,
            inputSchema={"type": "object", "properties": {}},
        )

        tool = _create_mcp_tool("test-server", mcp_tool, AsyncMock(), lock)

        assert tool.description == "My Tool Title"

    def test_description_fallback_to_server_name(self) -> None:
        lock = asyncio.Lock()
        mcp_tool = mcp_types.Tool(
            name="my_tool",
            description=None,
            inputSchema={"type": "object", "properties": {}},
        )

        tool = _create_mcp_tool("myserver", mcp_tool, AsyncMock(), lock)

        assert tool.description == "Tool from MCP server 'myserver'"


class TestPagination:
    """Test cursor-based pagination in list_tools."""

    async def test_single_page(self) -> None:
        session = AsyncMock()
        tools = [_make_mcp_tool("tool1"), _make_mcp_tool("tool2")]
        session.list_tools = AsyncMock(
            return_value=_make_list_tools_result(tools),
        )

        result = await _list_all_tools(session)
        assert len(result) == 2

    async def test_multiple_pages(self) -> None:
        session = AsyncMock()
        page1 = _make_list_tools_result([_make_mcp_tool("tool1")], next_cursor="page2")
        page2 = _make_list_tools_result([_make_mcp_tool("tool2")])
        session.list_tools = AsyncMock(side_effect=[page1, page2])

        result = await _list_all_tools(session)
        assert len(result) == 2
        assert result[0].name == "tool1"
        assert result[1].name == "tool2"


class TestErrorHandling:
    """Test error propagation from McpClient."""

    async def test_connection_failure_propagates(self) -> None:
        client = McpClient("test-server", _http_config())
        with (
            patch.object(
                McpClient,
                "_open_session",
                side_effect=ConnectionError("refused"),
            ),
            pytest.raises(ConnectionError, match="refused"),
        ):
            async with client:
                pass

    async def test_initialize_failure_propagates(self) -> None:
        client = McpClient("test-server", _http_config())
        with (
            patch.object(
                McpClient,
                "_open_session",
                side_effect=RuntimeError("handshake failed"),
            ),
            pytest.raises(RuntimeError, match="handshake failed"),
        ):
            async with client:
                pass
