"""Tests for WriteTool."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

if TYPE_CHECKING:
    from pathlib import Path

from clawwork.computer import LocalNativeComputer
from clawwork.exceptions import CLIError
from clawwork.tools import WriteTool


class TestWriteTool:
    """Basic WriteTool tests."""

    async def test_create_new_file(self, tmp_path: Path) -> None:
        """Writing to a new file creates it and returns success."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "hello.txt"
        result = await tool(description="test", file_path=str(target), content="hello world")
        assert result.output is not None
        assert result.error is None
        assert target.read_text() == "hello world"

    async def test_overwrite_existing_file(self, tmp_path: Path) -> None:
        """Writing to an existing file overwrites its content."""
        target = tmp_path / "existing.txt"
        target.write_text("old content")
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(description="test", file_path=str(target), content="new content")
        assert result.output is not None
        assert result.error is None
        assert target.read_text() == "new content"


class TestWriteToolOutputFormat:
    """Tests for WriteTool output message formatting."""

    async def test_new_file_success(self, tmp_path: Path) -> None:
        """New file write returns success output containing the path."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        path = str(tmp_path / "new.txt")
        result = await tool(description="test", file_path=path, content="data")
        assert result.output is not None
        assert result.error is None
        assert path in result.output

    async def test_overwrite_returns_output(self, tmp_path: Path) -> None:
        """Overwriting an existing file returns success output."""
        target = tmp_path / "update.txt"
        target.write_text("old")
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(description="test", file_path=str(target), content="line1\nline2\n")
        assert result.output is not None
        assert result.error is None
        assert target.read_text() == "line1\nline2\n"

    async def test_overwrite_output_contains_new_content(self, tmp_path: Path) -> None:
        """Overwrite output contains the new content for verification."""
        target = tmp_path / "snippet.txt"
        target.write_text("old")
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(description="test", file_path=str(target), content="alpha\nbeta\n")
        assert result.output is not None
        assert result.error is None
        assert "alpha" in result.output
        assert "beta" in result.output

    async def test_overwrite_empty_file(self, tmp_path: Path) -> None:
        """Overwriting an empty (0-byte) file succeeds."""
        target = tmp_path / "was_empty.txt"
        target.write_text("")
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(description="test", file_path=str(target), content="now has content")
        assert result.output is not None
        assert result.error is None
        assert target.read_text() == "now has content"

    async def test_empty_content_creates_empty_file(self, tmp_path: Path) -> None:
        """Empty content creates a 0-byte file."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "empty.txt"
        result = await tool(description="test", file_path=str(target), content="")
        assert result.error is None
        assert result.output is not None
        assert target.stat().st_size == 0

    async def test_success_error_is_none(self, tmp_path: Path) -> None:
        """Successful write never sets error (mutually exclusive)."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        path = str(tmp_path / "ok.txt")
        result = await tool(description="test", file_path=path, content="ok")
        assert result.error is None
        assert result.output is not None


class TestWriteToolSpecialContent:
    """Tests for content with special characters."""

    async def test_dollar_signs_not_expanded(self, tmp_path: Path) -> None:
        """Dollar signs are written literally, not shell-expanded."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "dollar.txt"
        content = "price is $100 and $HOME"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_backticks_not_executed(self, tmp_path: Path) -> None:
        """Backticks are written literally, not executed."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "backtick.txt"
        content = "run `echo hello` now"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_single_quotes(self, tmp_path: Path) -> None:
        """Single quotes are written literally."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "squote.txt"
        content = "it's a 'test'"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_double_quotes(self, tmp_path: Path) -> None:
        """Double quotes are written literally."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "dquote.txt"
        content = 'she said "hello"'
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_backslashes(self, tmp_path: Path) -> None:
        r"""Backslashes are written literally."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "backslash.txt"
        content = "path\\to\\file and \\n not newline"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_newlines_preserved(self, tmp_path: Path) -> None:
        """Newlines in content are preserved."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "newlines.txt"
        content = "line1\nline2\nline3\n"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_unicode_content(self, tmp_path: Path) -> None:
        """Unicode content (emoji, CJK) is written correctly."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "unicode.txt"
        content = "Hello \U0001f389 \u4e16\u754c caf\u00e9"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_heredoc_marker_in_content(self, tmp_path: Path) -> None:
        """Content containing the heredoc marker string is safe."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "marker.txt"
        content = "before\n__WRITE_PYEOF__\nafter"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content

    async def test_mixed_special_characters(self, tmp_path: Path) -> None:
        r"""Mixed special chars: $, `, ', \", \\, newlines, tabs."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "mixed.txt"
        content = "$HOME `cmd` 'single' \"double\" back\\slash\nnewline\ttab"
        result = await tool(description="test", file_path=str(target), content=content)
        assert result.error is None
        assert target.read_text() == content


class TestWriteToolDirectoryCreation:
    """Tests for automatic parent directory creation."""

    async def test_creates_nested_parent_directories(self, tmp_path: Path) -> None:
        """Non-existent parent directories are created automatically."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = tmp_path / "a" / "b" / "c" / "deep.txt"
        result = await tool(description="test", file_path=str(target), content="deep")
        assert result.error is None
        assert target.read_text() == "deep"

    async def test_existing_parent_directories_ok(self, tmp_path: Path) -> None:
        """Existing parent directories do not cause errors."""
        subdir = tmp_path / "existing"
        subdir.mkdir()
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        target = subdir / "file.txt"
        result = await tool(description="test", file_path=str(target), content="content")
        assert result.error is None
        assert target.read_text() == "content"


class TestWriteToolErrors:
    """Tests for error conditions."""

    async def test_path_is_directory(self, tmp_path: Path) -> None:
        """Writing to a path that is a directory returns error."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(description="test", file_path=str(tmp_path), content="data")
        assert result.error is not None
        assert result.output is None

    async def test_relative_path_rejected(self) -> None:
        """Relative paths are rejected with a clear error message."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(description="test", file_path="relative/path.txt", content="data")
        assert result.error is not None
        assert "absolute" in result.error.lower()

    async def test_failure_output_is_none(self, tmp_path: Path) -> None:
        """Failed write never sets output (mutually exclusive)."""
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(description="test", file_path=str(tmp_path), content="data")
        assert result.output is None
        assert result.error is not None


class TestWriteToolCLIError:
    """Tests for WriteTool handling of CLIError (infrastructure failures)."""

    async def test_cli_error_returns_error_result(self) -> None:
        """CLIError from computer.run is caught and returned as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("sandbox crashed"))
        tool = WriteTool(computer)
        result = await tool(description="test", file_path="/mock/test.txt", content="data")
        assert result.error is not None
        assert "sandbox crashed" in result.error

    async def test_cli_error_includes_system_message(self) -> None:
        """CLIError result includes a system message for the agent."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("timeout"))
        tool = WriteTool(computer)
        result = await tool(description="test", file_path="/mock/test.txt", content="data")
        assert result.system is not None

    async def test_cli_error_output_is_none(self) -> None:
        """CLIError result has no output."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("boom"))
        tool = WriteTool(computer)
        result = await tool(description="test", file_path="/mock/test.txt", content="data")
        assert result.output is None
