# ruff: noqa: S108, PLR2004
"""Tests for PresentToUserTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from hexagent.tools.ui.present_to_user import (
    _DELIM,
    _EXT_MIME_MAP,
    _PREFIX_COPIED,
    _PREFIX_ERR,
    _PREFIX_OK,
    _SCRIPT_BODY,
    PresentToUserTool,
    _build_command,
    _parse_output,
)
from hexagent.types import CLIResult, PresentToUserToolParams

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_computer(stdout: str = "", stderr: str = "", exit_code: int = 0) -> AsyncMock:
    """Create a mock Computer that returns a fixed CLIResult."""
    computer = AsyncMock()
    computer.run = AsyncMock(return_value=CLIResult(stdout=stdout, stderr=stderr, exit_code=exit_code))
    return computer


def _make_tool(computer: AsyncMock, output_dir: str = "/mnt/user-data/outputs") -> PresentToUserTool:
    return PresentToUserTool(computer=computer, output_dir=output_dir)


def _ok_line(output_path: str, mime_type: str) -> str:
    return f"{_PREFIX_OK}{_DELIM}{output_path}{_DELIM}{mime_type}"


def _copied_line(output_path: str, mime_type: str, original: str) -> str:
    return f"{_PREFIX_COPIED}{_DELIM}{output_path}{_DELIM}{mime_type}{_DELIM}{original}"


def _err_line(message: str) -> str:
    return f"{_PREFIX_ERR}{_DELIM}{message}"


# ---------------------------------------------------------------------------
# _parse_output unit tests
# ---------------------------------------------------------------------------


class TestParseOutput:
    """Tests for _parse_output (pure function, no Computer needed)."""

    def test_single_file_in_output_dir(self) -> None:
        stdout = _ok_line("/mnt/user-data/outputs/report.html", "text/html")
        result = _parse_output(stdout)

        assert result.error is None
        assert result.output is not None
        assert "<file_path>/mnt/user-data/outputs/report.html</file_path>" in result.output
        assert "<mime_type>text/html</mime_type>" in result.output
        assert "Files copied:" not in result.output

    def test_single_file_copied(self) -> None:
        stdout = _copied_line(
            "/mnt/user-data/outputs/new_web_demo.html",
            "text/html",
            "/home/claude/new_web_demo.html",
        )
        result = _parse_output(stdout)

        assert result.error is None
        assert result.output is not None
        assert "<file_path>/mnt/user-data/outputs/new_web_demo.html</file_path>" in result.output
        assert "Files copied:" in result.output
        assert "Copied /home/claude/new_web_demo.html to /mnt/user-data/outputs/new_web_demo.html" in result.output

    def test_multiple_files_some_copied(self) -> None:
        stdout = "\n".join(
            [
                _ok_line("/mnt/user-data/outputs/existing.txt", "text/plain"),
                _copied_line("/mnt/user-data/outputs/demo.py", "text/x-python", "/home/claude/demo.py"),
            ]
        )
        result = _parse_output(stdout)

        assert result.error is None
        assert result.output is not None
        assert result.output.count("<file>") == 2
        assert "Copied /home/claude/demo.py to /mnt/user-data/outputs/demo.py" in result.output
        # The in-place file should not appear in the copy notice
        copied_section = result.output.split("Files copied:")[-1]
        assert "existing.txt" not in copied_section

    def test_single_error(self) -> None:
        stdout = _err_line("Path does not exist: /no/such/file.txt")
        result = _parse_output(stdout)

        assert result.error is not None
        assert "Path does not exist: /no/such/file.txt" in result.error
        assert result.output is None

    def test_directory_path_error(self) -> None:
        stdout = _err_line("Path is not a file: /home/claude")
        result = _parse_output(stdout)

        assert result.error is not None
        assert "Path is not a file: /home/claude" in result.error

    def test_multiple_errors_all_reported(self) -> None:
        stdout = "\n".join(
            [
                _err_line("Path does not exist: /missing/a.txt"),
                _err_line("Path does not exist: /missing/b.txt"),
            ]
        )
        result = _parse_output(stdout)

        assert result.error is not None
        assert "/missing/a.txt" in result.error
        assert "/missing/b.txt" in result.error

    def test_one_error_fails_entire_call(self) -> None:
        """Even if some files are valid, one error fails everything."""
        stdout = "\n".join(
            [
                _copied_line("/mnt/user-data/outputs/good.txt", "text/plain", "/home/claude/good.txt"),
                _err_line("Path does not exist: /no/such/file.txt"),
            ]
        )
        result = _parse_output(stdout)

        assert result.error is not None
        assert result.output is None


# ---------------------------------------------------------------------------
# _build_command tests
# ---------------------------------------------------------------------------


class TestBuildCommand:
    """Tests for _build_command (pure function)."""

    def test_contains_output_dir(self) -> None:
        cmd = _build_command(["/a.txt"], "/mnt/outputs")
        assert "/mnt/outputs" in cmd

    def test_contains_all_filepaths(self) -> None:
        cmd = _build_command(["/a.txt", "/b.txt"], "/out")
        assert "/a.txt" in cmd
        assert "/b.txt" in cmd

    def test_quotes_special_characters(self) -> None:
        cmd = _build_command(["/path/with spaces/file.txt"], "/out")
        assert "'/path/with spaces/file.txt'" in cmd

    def test_embedded_script_normalized_to_lf(self) -> None:
        """Command string should not carry CR characters into bash -c payload."""
        cmd = _build_command(["/a.txt"], "/out")
        assert "\r" not in cmd


# ---------------------------------------------------------------------------
# _EXT_MIME_MAP / generated script tests
# ---------------------------------------------------------------------------


class TestExtMimeMap:
    """Tests for the extension→MIME map and its bash generation."""

    def test_map_is_not_empty(self) -> None:
        assert len(_EXT_MIME_MAP) > 0

    @pytest.mark.parametrize(
        ("ext", "expected_mime"),
        [
            ("md", "text/markdown"),
            ("css", "text/css"),
            ("js", "application/javascript"),
            ("ts", "application/typescript"),
            ("py", "text/x-python"),
            ("yaml", "application/x-yaml"),
            ("yml", "application/x-yaml"),
            ("toml", "application/toml"),
            ("csv", "text/csv"),
            ("mp3", "audio/mpeg"),
            ("webm", "video/webm"),
            ("zip", "application/zip"),
            ("wasm", "application/wasm"),
            ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ],
    )
    def test_key_extensions_present(self, ext: str, expected_mime: str) -> None:
        assert _EXT_MIME_MAP[ext] == expected_mime

    def test_all_map_entries_in_generated_script(self) -> None:
        """Every MIME type from the map appears in the baked script body."""
        for mime in set(_EXT_MIME_MAP.values()):
            assert mime in _SCRIPT_BODY, f"{mime} missing from generated script"

    def test_all_extensions_in_generated_script(self) -> None:
        """Every extension from the map appears in the baked script body."""
        for ext in _EXT_MIME_MAP:
            assert ext in _SCRIPT_BODY, f"extension {ext!r} missing from generated script"


# ---------------------------------------------------------------------------
# PresentToUserTool.execute integration tests (with mock Computer)
# ---------------------------------------------------------------------------


class TestPresentToUserToolExecute:
    """Tests for PresentToUserTool.execute via mock Computer."""

    async def test_passes_output_to_parse(self) -> None:
        stdout = _ok_line("/mnt/user-data/outputs/f.txt", "text/plain")
        computer = _make_computer(stdout=stdout)
        tool = _make_tool(computer)

        result = await tool.execute(PresentToUserToolParams(filepaths=["/mnt/user-data/outputs/f.txt"]))

        assert result.error is None
        assert "<file_path>/mnt/user-data/outputs/f.txt</file_path>" in (result.output or "")

    async def test_computer_run_failure(self) -> None:
        computer = _make_computer(stderr="bash: file: command not found", exit_code=127)
        tool = _make_tool(computer)

        result = await tool.execute(PresentToUserToolParams(filepaths=["/some/file.txt"]))

        assert result.error is not None
        assert "command not found" in result.error

    async def test_single_computer_run_call(self) -> None:
        stdout = "\n".join(
            [
                _copied_line("/mnt/user-data/outputs/a.txt", "text/plain", "/a.txt"),
                _copied_line("/mnt/user-data/outputs/b.txt", "text/plain", "/b.txt"),
            ]
        )
        computer = _make_computer(stdout=stdout)
        tool = _make_tool(computer)

        await tool.execute(PresentToUserToolParams(filepaths=["/a.txt", "/b.txt"]))

        assert computer.run.call_count == 1

    async def test_call_validates_empty_filepaths(self) -> None:
        computer = _make_computer()
        tool = _make_tool(computer, output_dir="/tmp/out")

        result = await tool(filepaths=[])

        assert result.error is not None
        assert "tool_call_error" in result.error

    @pytest.mark.parametrize("output_dir", ["/mnt/user-data/outputs", "/custom/output"])
    async def test_output_dir_in_command(self, output_dir: str) -> None:
        stdout = _copied_line(f"{output_dir}/f.txt", "text/plain", "/f.txt")
        computer = _make_computer(stdout=stdout)
        tool = _make_tool(computer, output_dir=output_dir)

        await tool.execute(PresentToUserToolParams(filepaths=["/f.txt"]))

        cmd = computer.run.call_args[0][0]
        assert output_dir in cmd
