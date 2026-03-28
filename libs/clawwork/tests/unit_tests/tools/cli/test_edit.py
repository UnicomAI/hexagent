"""Tests for EditTool."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from clawwork.computer import LocalNativeComputer
from clawwork.exceptions import CLIError
from clawwork.tools import EditTool

if TYPE_CHECKING:
    from pathlib import Path


class TestEditTool:
    """Tests for EditTool basic functionality."""

    async def test_unique_replacement(self, tmp_path: Path) -> None:
        """Single unique match is replaced."""
        path = tmp_path / "test.txt"
        path.write_text("hello world\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="hello",
            new_string="goodbye",
        )
        assert result.output is not None
        assert path.read_text() == "goodbye world\n"

    async def test_replace_all(self, tmp_path: Path) -> None:
        """All occurrences are replaced when replace_all is True."""
        path = tmp_path / "test.txt"
        path.write_text("aaa bbb aaa\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="aaa",
            new_string="ccc",
            replace_all=True,
        )
        assert result.output is not None
        assert path.read_text() == "ccc bbb ccc\n"

    async def test_multi_line_replacement(self, tmp_path: Path) -> None:
        """Multi-line old_string is matched and replaced."""
        path = tmp_path / "test.txt"
        path.write_text("line1\nline2\nline3\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="line1\nline2",
            new_string="combined",
        )
        assert result.output is not None
        assert path.read_text() == "combined\nline3\n"

    async def test_special_characters(self, tmp_path: Path) -> None:
        """Special shell characters ($, quotes, backticks) are handled literally."""
        content = """price is $100 and "quoted" and 'single' and `backtick`\n"""
        path = tmp_path / "test.txt"
        path.write_text(content)
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string='$100 and "quoted"',
            new_string="replaced",
        )
        assert result.output is not None
        assert "replaced" in path.read_text()
        assert "$100" not in path.read_text()

    async def test_empty_new_string_deletes(self, tmp_path: Path) -> None:
        """Empty new_string effectively deletes the matched text."""
        path = tmp_path / "test.txt"
        path.write_text("keep this remove this keep that\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string=" remove this",
            new_string="",
        )
        assert result.output is not None
        assert path.read_text() == "keep this keep that\n"


class TestEditToolErrors:
    """Tests for EditTool error cases."""

    async def test_non_unique_without_replace_all(self, tmp_path: Path) -> None:
        """Multiple matches without replace_all returns error."""
        path = tmp_path / "test.txt"
        path.write_text("foo bar foo\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="foo",
            new_string="baz",
        )
        assert result.error is not None
        assert "2 matches" in result.error
        assert "replace_all" in result.error
        # File should be unchanged
        assert path.read_text() == "foo bar foo\n"

    async def test_string_not_found(self, tmp_path: Path) -> None:
        """old_string not in file returns error."""
        path = tmp_path / "test.txt"
        path.write_text("hello world\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="nonexistent",
            new_string="something",
        )
        assert result.error is not None
        assert "not found" in result.error

    async def test_same_old_and_new(self, tmp_path: Path) -> None:
        """old_string == new_string returns error."""
        path = tmp_path / "test.txt"
        path.write_text("hello\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="hello",
            new_string="hello",
        )
        assert result.error is not None
        assert "No changes" in result.error

    async def test_file_not_found(self, tmp_path: Path) -> None:
        """Non-existent file returns error with CWD context."""
        nonexistent = tmp_path / "nonexistent_file_edit_test.txt"
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(nonexistent),
            old_string="x",
            new_string="y",
        )
        assert result.error is not None
        assert "does not exist" in result.error.lower()
        assert "Current working directory" in result.error

    async def test_empty_old_string(self, tmp_path: Path) -> None:
        """Empty old_string returns error."""
        path = tmp_path / "test.txt"
        path.write_text("hello\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="",
            new_string="something",
        )
        assert result.error is not None
        assert "empty" in result.error.lower()


class TestEditToolOutputFormat:
    """Tests for EditTool output/error formatting."""

    async def test_success_sets_output_not_error(self, tmp_path: Path) -> None:
        """Successful edit sets output and not error."""
        path = tmp_path / "test.txt"
        path.write_text("old\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="old",
            new_string="new",
        )
        assert result.output is not None
        assert result.error is None
        assert path.read_text() == "new\n"

    async def test_replace_all_success(self, tmp_path: Path) -> None:
        """replace_all=True replaces all and returns success output."""
        path = tmp_path / "test.txt"
        path.write_text("aaa bbb aaa\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="aaa",
            new_string="ccc",
            replace_all=True,
        )
        assert result.output is not None
        assert result.error is None
        assert path.read_text() == "ccc bbb ccc\n"

    async def test_error_sets_error_not_output(self, tmp_path: Path) -> None:
        """Failed edit sets error and not output."""
        path = tmp_path / "test.txt"
        path.write_text("hello\n")
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path=str(path),
            old_string="missing",
            new_string="something",
        )
        assert result.error is not None
        assert result.output is None


class TestEditToolCLIError:
    """Tests for EditTool handling of CLIError (infrastructure failures)."""

    async def test_cli_error_returns_error_result(self) -> None:
        """CLIError from computer.run is caught and returned as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("sandbox crashed"))
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path="/any/path",
            old_string="x",
            new_string="y",
        )
        assert result.error is not None
        assert "sandbox crashed" in result.error

    async def test_cli_error_includes_system_message(self) -> None:
        """CLIError result includes a system message for the agent."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("timeout"))
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path="/any/path",
            old_string="x",
            new_string="y",
        )
        assert result.system is not None

    async def test_cli_error_output_is_none(self) -> None:
        """CLIError result has no output."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("boom"))
        tool = EditTool(computer)
        result = await tool(
            description="test",
            file_path="/any/path",
            old_string="x",
            new_string="y",
        )
        assert result.output is None
