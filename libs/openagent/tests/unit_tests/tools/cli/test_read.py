"""Tests for ReadTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from openagent.computer import LocalNativeComputer
from openagent.exceptions import CLIError
from openagent.tools import ReadTool
from openagent.tools.cli.read import _LINE_SEPARATOR, _truncate_long_lines, read_file
from openagent.types import CLIResult


@pytest.fixture
def computer() -> LocalNativeComputer:
    return LocalNativeComputer()


@pytest.fixture
def tool(computer: LocalNativeComputer) -> ReadTool:
    return ReadTool(computer)


@pytest.fixture
def sample_file(tmp_path: pytest.TempPathFactory) -> str:
    """Text file with 10 numbered lines."""
    f = tmp_path / "sample.txt"  # type: ignore[operator]
    f.write_text("".join(f"line{i}\n" for i in range(1, 11)))
    return str(f)


@pytest.fixture
def empty_file(tmp_path: pytest.TempPathFactory) -> str:
    f = tmp_path / "empty.txt"  # type: ignore[operator]
    f.write_text("")
    return str(f)


@pytest.fixture
def binary_file(tmp_path: pytest.TempPathFactory) -> str:
    f = tmp_path / "binary.bin"  # type: ignore[operator]
    f.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")
    return str(f)


@pytest.fixture
def long_line_file(tmp_path: pytest.TempPathFactory) -> str:
    """File with a single line of 3000 characters."""
    f = tmp_path / "longline.txt"  # type: ignore[operator]
    f.write_text("A" * 3000 + "\n")
    return str(f)


# ---------------------------------------------------------------------------
# TestReadTool — integration tests with real LocalNativeComputer
# ---------------------------------------------------------------------------


class TestReadTool:
    """Core ReadTool tests."""

    def test_name(self, tool: ReadTool) -> None:
        """ReadTool name is 'read'."""
        assert tool.name == "read"

    async def test_read_file(self, tool: ReadTool, sample_file: str) -> None:
        """Read a text file and get numbered output."""
        result = await tool(file_path=sample_file)
        assert result.output is not None
        assert "line1" in result.output
        assert result.error is None

    async def test_line_numbers_format(self, tool: ReadTool, sample_file: str) -> None:
        """Output uses numbered format: number + separator + content."""
        result = await tool(file_path=sample_file)
        assert result.output is not None
        first_line = result.output.split("\n")[0]
        # Format: right-justified number, separator (→), then content
        assert _LINE_SEPARATOR in first_line
        assert "line1" in first_line

    async def test_all_lines_present(self, tool: ReadTool, sample_file: str) -> None:
        """All 10 lines are present in the output."""
        result = await tool(file_path=sample_file)
        assert result.output is not None
        for i in range(1, 11):
            assert f"line{i}" in result.output

    async def test_nonexistent_file(self, tool: ReadTool, tmp_path: pytest.TempPathFactory) -> None:
        """Non-existent file returns error."""
        path = str(tmp_path) + "/nonexistent.txt"
        result = await tool(file_path=path)
        assert result.error is not None
        assert "does not exist" in result.error
        assert result.output is None

    async def test_directory_returns_error(self, tool: ReadTool, tmp_path: pytest.TempPathFactory) -> None:
        """Reading a directory returns error."""
        result = await tool(file_path=str(tmp_path))
        assert result.error is not None
        assert "directory" in result.error.lower()
        assert result.output is None

    async def test_empty_file(self, tool: ReadTool, empty_file: str) -> None:
        """Empty file returns warning about 0 lines."""
        result = await tool(file_path=empty_file)
        assert result.error is not None
        assert "0 lines" in result.error
        assert result.output is None

    async def test_binary_file_rejected(self, tool: ReadTool, binary_file: str) -> None:
        """Binary file returns error."""
        result = await tool(file_path=binary_file)
        assert result.error is not None
        assert "binary" in result.error.lower()
        assert result.output is None


# ---------------------------------------------------------------------------
# TestReadToolOffset — offset and limit behavior
# ---------------------------------------------------------------------------


class TestReadToolOffset:
    """Tests for offset and limit parameters."""

    async def test_offset_skips_lines(self, tool: ReadTool, sample_file: str) -> None:
        """offset=5 skips first 4 lines, starts at line 5."""
        result = await tool(file_path=sample_file, offset=5)
        assert result.output is not None
        assert "line5" in result.output
        assert "line4" not in result.output

    async def test_limit_caps_output(self, tool: ReadTool, sample_file: str) -> None:
        """limit=3 returns exactly 3 lines."""
        result = await tool(file_path=sample_file, limit=3)
        assert result.output is not None
        non_empty = [line for line in result.output.strip().split("\n") if line.strip()]
        expected_lines = 3
        assert len(non_empty) == expected_lines

    async def test_offset_and_limit(self, tool: ReadTool, sample_file: str) -> None:
        """offset=3, limit=3 returns lines 3-5."""
        result = await tool(file_path=sample_file, offset=3, limit=3)
        assert result.output is not None
        assert "line3" in result.output
        assert "line5" in result.output
        assert "line2" not in result.output
        assert "line6" not in result.output

    async def test_offset_past_end(self, tool: ReadTool, sample_file: str) -> None:
        """Offset past end of file returns error."""
        result = await tool(file_path=sample_file, offset=100)
        assert result.error is not None
        assert result.output is None

    async def test_limit_past_end(self, tool: ReadTool, sample_file: str) -> None:
        """Limit larger than file returns all lines (no error)."""
        result = await tool(file_path=sample_file, limit=9999)
        assert result.output is not None
        assert "line1" in result.output
        assert "line10" in result.output
        assert result.error is None

    async def test_offset_zero_labels_from_zero(self, tool: ReadTool, sample_file: str) -> None:
        """offset=0 labels the first line as line 0."""
        result = await tool(file_path=sample_file, offset=0, limit=1)
        assert result.output is not None
        # First line should be labeled as 0
        assert result.output.startswith("     0")

    async def test_offset_one_labels_from_one(self, tool: ReadTool, sample_file: str) -> None:
        """offset=1 labels the first line as line 1."""
        result = await tool(file_path=sample_file, offset=1, limit=1)
        assert result.output is not None
        # First line should be labeled as 1
        assert result.output.startswith("     1")


# ---------------------------------------------------------------------------
# TestReadToolCLIError — infrastructure failure handling
# ---------------------------------------------------------------------------


class TestReadToolCLIError:
    """Tests for CLIError (infrastructure failures)."""

    async def test_cli_error_returns_error_result(self) -> None:
        """CLIError from computer.run is caught and returned as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("sandbox crashed"))
        tool = ReadTool(computer)
        result = await tool(file_path="/any/path")
        assert result.error is not None
        assert "sandbox crashed" in result.error

    async def test_cli_error_includes_system_message(self) -> None:
        """CLIError result includes a system message for the agent."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("timeout"))
        tool = ReadTool(computer)
        result = await tool(file_path="/any/path")
        assert result.system is not None
        assert "Do not retry" in result.system

    async def test_cli_error_output_is_none(self) -> None:
        """CLIError result has no output."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("boom"))
        tool = ReadTool(computer)
        result = await tool(file_path="/any/path")
        assert result.output is None


# ---------------------------------------------------------------------------
# TestReadFileFunction — unit tests for the read_file() function
# ---------------------------------------------------------------------------


class TestReadFileFunction:
    """Tests for the standalone read_file() function."""

    async def test_returns_cli_result(self, computer: LocalNativeComputer, sample_file: str) -> None:
        """read_file() returns a CLIResult."""
        result = await read_file(computer, sample_file)
        assert isinstance(result, CLIResult)
        assert result.exit_code == 0

    async def test_content_has_line_numbers(self, computer: LocalNativeComputer, sample_file: str) -> None:
        """Output contains separator-separated line numbers."""
        result = await read_file(computer, sample_file)
        assert _LINE_SEPARATOR in result.stdout
        assert "line1" in result.stdout

    async def test_nonexistent_returns_error(self, computer: LocalNativeComputer, tmp_path: pytest.TempPathFactory) -> None:
        """Non-existent file returns CLIResult with non-zero exit_code."""
        path = str(tmp_path) + "/nonexistent.txt"
        result = await read_file(computer, path)
        assert result.exit_code != 0
        assert "does not exist" in result.stderr

    async def test_empty_file_returns_warning(self, computer: LocalNativeComputer, empty_file: str) -> None:
        """Empty file returns CLIResult with warning about 0 lines."""
        result = await read_file(computer, empty_file)
        assert result.exit_code == 1
        assert "0 lines" in result.stderr


# ---------------------------------------------------------------------------
# TestTruncateLongLines — pure unit tests
# ---------------------------------------------------------------------------


class TestTruncateLongLines:
    """Tests for the _truncate_long_lines() helper."""

    def test_short_lines_unchanged(self) -> None:
        """Lines within limit are not modified."""
        content = f"     1{_LINE_SEPARATOR}hello world"
        assert _truncate_long_lines(content) == content

    def test_long_line_truncated(self) -> None:
        """Lines exceeding _MAX_LINE_LENGTH are truncated."""
        prefix = f"     1{_LINE_SEPARATOR}"
        body = "A" * 3000
        content = prefix + body
        result = _truncate_long_lines(content)
        assert result == prefix + "A" * 2000

    def test_empty_content(self) -> None:
        """Empty string returns empty string."""
        assert _truncate_long_lines("") == ""

    def test_no_separator_line_preserved(self) -> None:
        """Lines without separator are passed through unchanged."""
        content = "no separator here at all"
        assert _truncate_long_lines(content) == content

    def test_multiple_lines(self) -> None:
        """Only lines exceeding the limit are truncated."""
        short = f"     1{_LINE_SEPARATOR}short"
        long_body = "B" * 3000
        long_line = f"     2{_LINE_SEPARATOR}" + long_body
        content = short + "\n" + long_line
        result = _truncate_long_lines(content)
        lines = result.split("\n")
        assert lines[0] == short
        assert lines[1] == f"     2{_LINE_SEPARATOR}" + "B" * 2000


# ---------------------------------------------------------------------------
# TestReadToolLongLines — integration test for line truncation
# ---------------------------------------------------------------------------


class TestReadToolLongLines:
    """Integration test for long line truncation."""

    async def test_long_lines_truncated(self, tool: ReadTool, long_line_file: str) -> None:
        """Lines longer than 2000 chars are truncated in output."""
        result = await tool(file_path=long_line_file)
        assert result.output is not None
        first_line = result.output.split("\n")[0]
        # Extract content after the separator
        sep_idx = first_line.find(_LINE_SEPARATOR)
        body = first_line[sep_idx + len(_LINE_SEPARATOR) :]
        from openagent.tools.cli.read import _MAX_LINE_LENGTH

        assert len(body) == _MAX_LINE_LENGTH
