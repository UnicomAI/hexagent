"""Tests for hexagent.mcp._tool — McpTool and result conversion."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import mcp.types as mcp_types
from pydantic import BaseModel, Field

from hexagent.mcp._tool import McpTool, _convert_result
from hexagent.types import Base64Source


def _make_text_content(text: str) -> mcp_types.TextContent:
    return mcp_types.TextContent(type="text", text=text)


def _make_image_content(data: str, mime_type: str = "image/png") -> mcp_types.ImageContent:
    return mcp_types.ImageContent(type="image", data=data, mimeType=mime_type)


def _make_result(
    content: list[mcp_types.TextContent | mcp_types.ImageContent] | None = None,
    *,
    is_error: bool = False,
    structured_content: dict[str, object] | None = None,
) -> mcp_types.CallToolResult:
    return mcp_types.CallToolResult(
        content=list(content) if content else [],
        isError=is_error,
        structuredContent=structured_content,
    )


class TestConvertResult:
    """Test _convert_result directly."""

    def test_single_text_to_output(self) -> None:
        result = _convert_result(_make_result([_make_text_content("hello")]))
        assert result.output == "hello"
        assert result.error is None

    def test_multiple_text_blocks_joined(self) -> None:
        result = _convert_result(
            _make_result(
                [
                    _make_text_content("line1"),
                    _make_text_content("line2"),
                ]
            )
        )
        assert result.output == "line1\nline2"

    def test_error_result(self) -> None:
        result = _convert_result(
            _make_result(
                [_make_text_content("something went wrong")],
                is_error=True,
            )
        )
        assert result.error == "something went wrong"
        assert result.output is None

    def test_error_without_text(self) -> None:
        result = _convert_result(_make_result(is_error=True))
        assert result.error == "MCP tool returned an error"

    def test_image_content(self) -> None:
        result = _convert_result(_make_result([_make_image_content("base64data")]))
        assert result.images == (Base64Source(data="base64data", media_type="image/png"),)
        assert result.output is None

    def test_multiple_images_kept(self) -> None:
        result = _convert_result(
            _make_result(
                [
                    _make_image_content("first"),
                    _make_image_content("second", mime_type="image/jpeg"),
                ]
            )
        )
        assert result.images == (
            Base64Source(data="first", media_type="image/png"),
            Base64Source(data="second", media_type="image/jpeg"),
        )

    def test_text_and_image(self) -> None:
        result = _convert_result(
            _make_result(
                [
                    _make_text_content("description"),
                    _make_image_content("imgdata"),
                ]
            )
        )
        assert result.output == "description"
        assert result.images == (Base64Source(data="imgdata", media_type="image/png"),)

    def test_image_media_type_captured(self) -> None:
        result = _convert_result(_make_result([_make_image_content("data", mime_type="image/webp")]))
        assert result.images == (Base64Source(data="data", media_type="image/webp"),)

    def test_structured_content_fallback(self) -> None:
        result = _convert_result(_make_result(structured_content={"key": "value"}))
        assert result.output == json.dumps({"key": "value"})

    def test_empty_result(self) -> None:
        result = _convert_result(_make_result())
        assert result.output is None
        assert result.error is None
        assert result.images == ()


class TestMcpToolExecution:
    """Test McpTool.execute with mocked session."""

    @staticmethod
    def _make_tool(session: AsyncMock) -> McpTool:
        class Params(BaseModel):
            query: str = Field(description="Search query")

        return McpTool(
            name="mcp__test__search",
            description="Search tool",
            args_schema=Params,
            session=session,
            mcp_tool_name="search",
            session_lock=asyncio.Lock(),
        )

    async def test_calls_session_with_correct_args(self) -> None:
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_make_result([_make_text_content("found it")]))
        tool = self._make_tool(session)

        result = await tool(query="python")

        session.call_tool.assert_called_once_with("search", {"query": "python"})
        assert result.output == "found it"

    async def test_error_result_propagated(self) -> None:
        session = AsyncMock()
        session.call_tool = AsyncMock(
            return_value=_make_result(
                [_make_text_content("not found")],
                is_error=True,
            )
        )
        tool = self._make_tool(session)

        result = await tool(query="nonexistent")

        assert result.error == "not found"
        assert result.output is None

    async def test_session_lock_serializes_calls(self) -> None:
        """Verify the lock is acquired during call_tool."""
        lock = asyncio.Lock()
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_make_result([_make_text_content("ok")]))

        class Params(BaseModel):
            x: str

        tool = McpTool(
            name="mcp__test__t",
            description="test",
            args_schema=Params,
            session=session,
            mcp_tool_name="t",
            session_lock=lock,
        )

        # Acquire lock externally, then verify tool awaits it
        lock_acquired = asyncio.Event()
        lock_released = asyncio.Event()

        async def hold_lock() -> None:
            async with lock:
                lock_acquired.set()
                await lock_released.wait()

        holder = asyncio.create_task(hold_lock())
        await lock_acquired.wait()

        # Start tool call — should block on lock
        tool_task = asyncio.create_task(tool(x="test"))

        # Give event loop a chance to run
        await asyncio.sleep(0.01)
        assert not tool_task.done()

        # Release lock
        lock_released.set()
        await holder
        result = await tool_task
        assert result.output == "ok"

    async def test_optional_fields_excluded_when_unset(self) -> None:
        """Unset optional params must not be sent to the MCP server."""
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_make_result([_make_text_content("ok")]))

        class Params(BaseModel):
            query: str
            max_results: int | None = None
            verbose: bool | None = None

        tool = McpTool(
            name="mcp__test__search",
            description="Search",
            args_schema=Params,
            session=session,
            mcp_tool_name="search",
            session_lock=asyncio.Lock(),
        )

        # Call with only the required field
        await tool(query="hello")
        session.call_tool.assert_called_once_with("search", {"query": "hello"})

    async def test_explicit_optional_fields_included(self) -> None:
        """Explicitly provided optional params must be sent to the MCP server."""
        session = AsyncMock()
        session.call_tool = AsyncMock(return_value=_make_result([_make_text_content("ok")]))

        class Params(BaseModel):
            query: str
            max_results: int | None = None

        tool = McpTool(
            name="mcp__test__search",
            description="Search",
            args_schema=Params,
            session=session,
            mcp_tool_name="search",
            session_lock=asyncio.Lock(),
        )

        await tool(query="hello", max_results=5)
        session.call_tool.assert_called_once_with("search", {"query": "hello", "max_results": 5})

    async def test_tool_attributes(self) -> None:
        session = MagicMock()
        tool = self._make_tool(session)

        assert tool.name == "mcp__test__search"
        assert tool.description == "Search tool"
