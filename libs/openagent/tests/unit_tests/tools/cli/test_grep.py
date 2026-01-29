"""Tests for GrepTool."""

from __future__ import annotations

from unittest.mock import AsyncMock

from openagent.exceptions import CLIError
from openagent.tools import GrepTool
from openagent.tools.cli.grep import build_rg_command
from openagent.types import CLIResult, GrepToolParams

# ---------------------------------------------------------------------------
# build_rg_command
# ---------------------------------------------------------------------------


class TestBuildRgCommand:
    """Tests for the rg command builder."""

    def test_default_files_with_matches(self) -> None:
        """Default output_mode produces --files-with-matches."""
        params = GrepToolParams(pattern="TODO")
        cmd = build_rg_command(params)
        assert "--files-with-matches" in cmd
        assert cmd.startswith("rg ")

    def test_content_mode_with_line_numbers(self) -> None:
        """Content mode adds --line-number when show_line_numbers is True."""
        params = GrepToolParams(pattern="foo", output_mode="content")
        cmd = build_rg_command(params)
        assert "--line-number" in cmd
        assert "--files-with-matches" not in cmd

    def test_content_mode_without_line_numbers(self) -> None:
        """Content mode omits --line-number when show_line_numbers is False."""
        params = GrepToolParams.model_validate({"pattern": "foo", "output_mode": "content", "-n": False})
        cmd = build_rg_command(params)
        assert "--line-number" not in cmd

    def test_count_mode(self) -> None:
        """Count mode produces --count."""
        params = GrepToolParams(pattern="foo", output_mode="count")
        cmd = build_rg_command(params)
        assert "--count" in cmd
        assert "--files-with-matches" not in cmd

    def test_case_insensitive(self) -> None:
        """case_insensitive adds --ignore-case."""
        params = GrepToolParams.model_validate({"pattern": "foo", "-i": True})
        cmd = build_rg_command(params)
        assert "--ignore-case" in cmd

    def test_multiline(self) -> None:
        """Multiline adds --multiline --multiline-dotall."""
        params = GrepToolParams(pattern="foo", multiline=True)
        cmd = build_rg_command(params)
        assert "--multiline" in cmd
        assert "--multiline-dotall" in cmd

    def test_glob_filter(self) -> None:
        """Glob adds --glob with the pattern."""
        params = GrepToolParams(pattern="foo", glob="*.py")
        cmd = build_rg_command(params)
        assert "--glob" in cmd
        assert "*.py" in cmd

    def test_type_filter(self) -> None:
        """Type adds --type with the value."""
        params = GrepToolParams(pattern="foo", type="py")
        cmd = build_rg_command(params)
        assert "--type" in cmd
        assert "py" in cmd

    def test_after_context(self) -> None:
        """after_context adds -A flag in content mode."""
        params = GrepToolParams.model_validate({"pattern": "foo", "output_mode": "content", "-A": 3})
        cmd = build_rg_command(params)
        assert "-A 3" in cmd

    def test_before_context(self) -> None:
        """before_context adds -B flag in content mode."""
        params = GrepToolParams.model_validate({"pattern": "foo", "output_mode": "content", "-B": 2})
        cmd = build_rg_command(params)
        assert "-B 2" in cmd

    def test_combined_context(self) -> None:
        """Context adds -C flag in content mode."""
        params = GrepToolParams.model_validate({"pattern": "foo", "output_mode": "content", "-C": 5})
        cmd = build_rg_command(params)
        assert "-C 5" in cmd

    def test_context_flags_ignored_in_files_mode(self) -> None:
        """Context flags are omitted when output_mode is not content."""
        params = GrepToolParams.model_validate({"pattern": "foo", "output_mode": "files_with_matches", "-A": 3, "-B": 2, "-C": 1})
        cmd = build_rg_command(params)
        assert "-A" not in cmd
        assert "-B" not in cmd
        assert "-C" not in cmd

    def test_line_numbers_ignored_in_files_mode(self) -> None:
        """--line-number is omitted when output_mode is not content."""
        params = GrepToolParams(pattern="foo", output_mode="files_with_matches")
        cmd = build_rg_command(params)
        assert "--line-number" not in cmd

    def test_pattern_with_special_chars_is_quoted(self) -> None:
        """Pattern containing shell-special characters is quoted."""
        params = GrepToolParams(pattern="hello world")
        cmd = build_rg_command(params)
        # shlex.quote wraps in single quotes: 'hello world'
        assert "'hello world'" in cmd

    def test_path_with_spaces_is_quoted(self) -> None:
        """Path with spaces is shell-quoted."""
        params = GrepToolParams(pattern="foo", path="/my dir/code")
        cmd = build_rg_command(params)
        assert "'/my dir/code'" in cmd

    def test_double_dash_separator(self) -> None:
        """Command includes -- to separate flags from pattern."""
        params = GrepToolParams(pattern="-v")
        cmd = build_rg_command(params)
        assert " -- " in cmd

    def test_default_path_is_dot(self) -> None:
        """Default path is current directory '.'."""
        params = GrepToolParams(pattern="foo")
        cmd = build_rg_command(params)
        assert cmd.endswith(" .")


# ---------------------------------------------------------------------------
# GrepTool basics
# ---------------------------------------------------------------------------


class TestGrepTool:
    """Basic GrepTool tests."""

    def test_name(self) -> None:
        """GrepTool name is 'grep'."""
        tool = GrepTool(AsyncMock())
        assert tool.name == "grep"

    def test_args_schema(self) -> None:
        """GrepTool uses GrepToolParams."""
        assert GrepTool.args_schema is GrepToolParams

    async def test_execute_delegates_to_computer(self) -> None:
        """Execute builds and runs the rg command via computer."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="file.py\n", exit_code=0),
        )
        tool = GrepTool(computer)
        await tool(pattern="foo")
        computer.run.assert_called_once()
        cmd = computer.run.call_args[0][0]
        assert cmd.startswith("rg ")
        assert "foo" in cmd


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class TestGrepToolFilesOutput:
    """Tests for files_with_matches output formatting."""

    async def test_files_summary_header(self) -> None:
        """files_with_matches includes 'Found N files' header."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="a.py\nb.py\nc.py\n", exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo")
        assert result.output is not None
        assert result.output.startswith("Found 3 files")
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.py" in result.output

    async def test_single_file_singular(self) -> None:
        """Single file uses singular 'file' in header."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="only.py\n", exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo")
        assert result.output is not None
        assert "Found 1 file\n" in result.output

    async def test_no_matches_files(self) -> None:
        """No matches in files mode returns 'No files found'."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="", exit_code=1),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="nonexistent")
        assert result.output == "No files found"
        assert result.error is None

    async def test_head_limit(self) -> None:
        """head_limit truncates file results."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="a.py\nb.py\nc.py\nd.py\n", exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo", head_limit=2)
        assert result.output is not None
        assert "Found 2 file" in result.output
        assert "a.py" in result.output
        assert "b.py" in result.output
        assert "c.py" not in result.output

    async def test_offset(self) -> None:
        """Offset skips initial file results."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="a.py\nb.py\nc.py\n", exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo", offset=1)
        assert result.output is not None
        assert "a.py" not in result.output
        assert "b.py" in result.output
        assert "c.py" in result.output

    async def test_offset_and_limit(self) -> None:
        """Offset + head_limit work together."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(
                stdout="a.py\nb.py\nc.py\nd.py\ne.py\n",
                exit_code=0,
            ),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo", offset=1, head_limit=2)
        assert result.output is not None
        assert "Found 2 file" in result.output
        assert "limit: 2, offset: 1" in result.output
        assert "a.py" not in result.output
        assert "b.py" in result.output
        assert "c.py" in result.output
        assert "d.py" not in result.output

    async def test_limit_shown_in_header(self) -> None:
        """Header includes limit/offset when either is non-zero."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="a.py\nb.py\n", exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo", head_limit=5)
        assert result.output is not None
        assert "limit: 5, offset: 0" in result.output

    async def test_no_limit_offset_in_header_by_default(self) -> None:
        """Header omits limit/offset when both are zero."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="a.py\n", exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo")
        assert result.output is not None
        assert "limit:" not in result.output
        assert "offset:" not in result.output


class TestGrepToolCountOutput:
    """Tests for count output formatting."""

    async def test_count_summary(self) -> None:
        """Count mode includes occurrence summary at end."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(
                stdout="a.py:5\nb.py:3\n",
                exit_code=0,
            ),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo", output_mode="count")
        assert result.output is not None
        assert "a.py:5" in result.output
        assert "b.py:3" in result.output
        assert "Found 8 total occurrences across 2 files." in result.output

    async def test_count_single_file_singular(self) -> None:
        """Single file/occurrence uses singular form."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="a.py:1\n", exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="foo", output_mode="count")
        assert result.output is not None
        assert "1 total occurrence across 1 file." in result.output

    async def test_count_no_matches(self) -> None:
        """No matches in count mode includes zero-count summary."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="", exit_code=1),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="nonexistent", output_mode="count")
        assert result.output is not None
        assert "No matches found" in result.output
        assert "Found 0 total occurrences across 0 files." in result.output

    async def test_count_with_pagination(self) -> None:
        """Pagination applies to count results and shows in summary."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(
                stdout="a.py:5\nb.py:3\nc.py:2\n",
                exit_code=0,
            ),
        )
        tool = GrepTool(computer)
        result = await tool(
            pattern="foo",
            output_mode="count",
            offset=1,
            head_limit=1,
        )
        assert result.output is not None
        assert "a.py" not in result.output
        assert "b.py:3" in result.output
        assert "c.py" not in result.output
        assert "Found 3 total occurrences across 1 file." in result.output
        assert "with pagination = limit: 1, offset: 1" in result.output


class TestGrepToolContentOutput:
    """Tests for content output formatting."""

    async def test_content_returns_matching_lines(self) -> None:
        """Content mode returns matching lines."""
        computer = AsyncMock()
        rg_output = "file.py:10:def foo():\nfile.py:20:def bar():\n"
        computer.run = AsyncMock(
            return_value=CLIResult(stdout=rg_output, exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="def", output_mode="content")
        assert result.output is not None
        assert "file.py:10:def foo():" in result.output
        assert "file.py:20:def bar():" in result.output
        assert "[Showing results" not in result.output

    async def test_content_no_matches(self) -> None:
        """No matches in content mode returns 'No matches found'."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="", exit_code=1),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="nonexistent", output_mode="content")
        assert result.output == "No matches found"

    async def test_content_with_head_limit(self) -> None:
        """head_limit limits content lines and adds pagination footer."""
        computer = AsyncMock()
        rg_output = "a.py:1:line1\na.py:2:line2\na.py:3:line3\n"
        computer.run = AsyncMock(
            return_value=CLIResult(stdout=rg_output, exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="line", output_mode="content", head_limit=2)
        assert result.output is not None
        assert "line1" in result.output
        assert "line2" in result.output
        assert "line3" not in result.output
        assert "[Showing results with pagination" in result.output

    async def test_content_with_offset(self) -> None:
        """Offset skips initial content lines."""
        computer = AsyncMock()
        rg_output = "a.py:1:line1\na.py:2:line2\na.py:3:line3\n"
        computer.run = AsyncMock(
            return_value=CLIResult(stdout=rg_output, exit_code=0),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="line", output_mode="content", offset=1)
        assert result.output is not None
        assert "line1" not in result.output
        assert "line2" in result.output
        assert "line3" in result.output


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestGrepToolErrors:
    """Tests for error handling."""

    async def test_rg_error_returns_stderr(self) -> None:
        """Rg exit code >= 2 returns stderr as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(
                stdout="",
                stderr="regex parse error: unclosed bracket",
                exit_code=2,
            ),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="[invalid", output_mode="content")
        assert result.error is not None
        assert "regex parse error" in result.error
        assert result.output is None

    async def test_rg_error_fallback_message(self) -> None:
        """Rg exit code >= 2 with empty stderr uses fallback error."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="", stderr="", exit_code=2),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="[invalid")
        assert result.error is not None
        assert "exit code 2" in result.error

    async def test_cli_error_returns_error_result(self) -> None:
        """CLIError from computer.run is caught and returned as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("sandbox crashed"))
        tool = GrepTool(computer)
        result = await tool(pattern="foo")
        assert result.error is not None
        assert "sandbox crashed" in result.error

    async def test_cli_error_includes_system_message(self) -> None:
        """CLIError result includes a system message for the agent."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("timeout"))
        tool = GrepTool(computer)
        result = await tool(pattern="foo")
        assert result.system is not None
        assert "Do not retry" in result.system

    async def test_cli_error_output_is_none(self) -> None:
        """CLIError result has no output."""
        computer = AsyncMock()
        computer.run = AsyncMock(side_effect=CLIError("boom"))
        tool = GrepTool(computer)
        result = await tool(pattern="foo")
        assert result.output is None

    async def test_exit_code_1_is_not_an_error(self) -> None:
        """Rg exit code 1 (no matches) is not treated as error."""
        computer = AsyncMock()
        computer.run = AsyncMock(
            return_value=CLIResult(stdout="", stderr="", exit_code=1),
        )
        tool = GrepTool(computer)
        result = await tool(pattern="nonexistent")
        assert result.error is None
        assert result.output is not None
