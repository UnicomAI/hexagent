"""Tests for ToolResult.to_content_blocks() — content block formatting."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest

from clawwork.types import Base64Source, ToolResult, UrlSource


class TestAnthropicContentBlocks:
    """Tests for ToolResult.to_content_blocks("anthropic")."""

    def test_text_only(self) -> None:
        blocks = ToolResult(output="hello world").to_content_blocks("anthropic")
        assert blocks == [{"type": "text", "text": "hello world"}]

    def test_error_only(self) -> None:
        blocks = ToolResult(error="something failed").to_content_blocks("anthropic")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"
        assert "something failed" in blocks[0]["text"]

    def test_empty_result(self) -> None:
        blocks = ToolResult().to_content_blocks("anthropic")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "text"

    def test_base64_image(self) -> None:
        img = Base64Source(data="iVBOR", media_type="image/png")
        blocks = ToolResult(images=(img,)).to_content_blocks("anthropic")

        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"] == {
            "type": "base64",
            "media_type": "image/png",
            "data": "iVBOR",
        }

    def test_url_image(self) -> None:
        img = UrlSource(url="https://example.com/img.png")
        blocks = ToolResult(images=(img,)).to_content_blocks("anthropic")

        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"] == {
            "type": "url",
            "url": "https://example.com/img.png",
        }

    def test_text_and_image(self) -> None:
        img = Base64Source(data="abc", media_type="image/jpeg")
        blocks = ToolResult(output="Screenshot", images=(img,)).to_content_blocks("anthropic")

        text_blocks = [b for b in blocks if b["type"] == "text"]
        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(text_blocks) == 1
        assert text_blocks[0]["text"] == "Screenshot"
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"]["type"] == "base64"

    def test_multiple_images(self) -> None:
        img1 = Base64Source(data="first", media_type="image/png")
        img2 = UrlSource(url="https://example.com/second.jpg")
        blocks = ToolResult(output="Two images", images=(img1, img2)).to_content_blocks("anthropic")

        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) == 2
        assert image_blocks[0]["source"]["type"] == "base64"
        assert image_blocks[1]["source"]["type"] == "url"


class TestOpenAIContentBlocks:
    """Tests for ToolResult.to_content_blocks("openai")."""

    def test_text_only(self) -> None:
        blocks = ToolResult(output="hello world").to_content_blocks("openai")
        assert blocks == [{"type": "text", "text": "hello world"}]

    def test_base64_image(self) -> None:
        img = Base64Source(data="iVBOR", media_type="image/png")
        blocks = ToolResult(images=(img,)).to_content_blocks("openai")

        image_blocks = [b for b in blocks if b["type"] == "image_url"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"] == "data:image/png;base64,iVBOR"

    def test_url_image(self) -> None:
        img = UrlSource(url="https://example.com/img.png")
        blocks = ToolResult(images=(img,)).to_content_blocks("openai")

        image_blocks = [b for b in blocks if b["type"] == "image_url"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"] == "https://example.com/img.png"


class TestContentFormatParam:
    """Tests for to_langchain_tool content_format parameter."""

    def test_anthropic_format_produces_image_blocks(self) -> None:
        img = Base64Source(data="iVBOR", media_type="image/png")
        result = ToolResult(output="Screenshot", images=(img,))
        blocks = result.to_content_blocks("anthropic")
        image_blocks = [b for b in blocks if b["type"] == "image"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["source"]["type"] == "base64"

    def test_openai_format_produces_image_url_blocks(self) -> None:
        img = Base64Source(data="iVBOR", media_type="image/png")
        result = ToolResult(output="Screenshot", images=(img,))
        blocks = result.to_content_blocks("openai")
        image_blocks = [b for b in blocks if b["type"] == "image_url"]
        assert len(image_blocks) == 1
        assert image_blocks[0]["image_url"]["url"] == "data:image/png;base64,iVBOR"


class TestContentBlocksGeneral:
    """Format-agnostic tests."""

    def test_default_format_is_openai(self) -> None:
        result = ToolResult(output="hello")
        assert result.to_content_blocks() == result.to_content_blocks("openai")

    def test_unsupported_format_raises(self) -> None:
        result = ToolResult(output="hello")
        with pytest.raises(ValueError, match="Unsupported"):
            result.to_content_blocks("unknown")  # type: ignore[arg-type]

    def test_always_returns_list(self) -> None:
        text_only = ToolResult(output="hello").to_content_blocks()
        with_image = ToolResult(images=(Base64Source(data="x", media_type="image/png"),)).to_content_blocks()
        empty = ToolResult().to_content_blocks()

        assert isinstance(text_only, list)
        assert isinstance(with_image, list)
        assert isinstance(empty, list)

    def test_text_block_identical_across_formats(self) -> None:
        """Text blocks have the same structure in both formats."""
        result = ToolResult(output="hello")
        anthropic = result.to_content_blocks("anthropic")
        openai = result.to_content_blocks("openai")
        assert anthropic == openai
