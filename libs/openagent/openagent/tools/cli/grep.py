"""Grep tool for searching file contents.

This module provides the GrepTool class that enables agents to search
for patterns in files through a Computer interface. The heavy lifting
(command building and execution) lives in ``build_rg_command`` and
``run_ripgrep``; ``GrepTool`` is a thin formatting layer that converts
the raw ``CLIResult`` into a ``ToolResult``.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Literal

from openagent.exceptions import CLIError
from openagent.tools.base import BaseAgentTool
from openagent.types import CLIResult, GrepToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer


# ripgrep exit codes: 0 = matches found, 1 = no matches, >= 2 = error
_RG_ERROR_EXIT_CODE = 2


# ---------------------------------------------------------------------------
# Heavy implementation - builds and runs the ripgrep command
# ---------------------------------------------------------------------------


def build_rg_command(params: GrepToolParams) -> str:
    """Build a ripgrep command string from grep parameters.

    Maps ``GrepToolParams`` fields to ``rg`` CLI flags. The resulting
    command is safe to pass to a shell — all user-supplied values are
    quoted with ``shlex.quote``.

    Args:
        params: Validated grep parameters.

    Returns:
        Shell command string ready for execution.
    """
    parts: list[str] = ["rg"]

    # Output mode
    if params.output_mode == "files_with_matches":
        parts.append("--files-with-matches")
    elif params.output_mode == "count":
        parts.append("--count")
    # "content" is rg's default (no flag needed)

    # Flags only meaningful in content mode
    if params.output_mode == "content":
        if params.show_line_numbers:
            parts.append("--line-number")
        if params.after_context is not None:
            parts.extend(["-A", str(params.after_context)])
        if params.before_context is not None:
            parts.extend(["-B", str(params.before_context)])
        if params.context is not None:
            parts.extend(["-C", str(params.context)])

    # General flags
    if params.case_insensitive:
        parts.append("--ignore-case")
    if params.multiline:
        parts.extend(["--multiline", "--multiline-dotall"])
    if params.glob is not None:
        parts.extend(["--glob", shlex.quote(params.glob)])
    if params.type is not None:
        parts.extend(["--type", shlex.quote(params.type)])

    # "--" separates flags from the pattern to prevent patterns like
    # "-foo" from being interpreted as flags.
    parts.append("--")
    parts.append(shlex.quote(params.pattern))
    parts.append(shlex.quote(params.path))

    return " ".join(parts)


async def run_ripgrep(computer: Computer, params: GrepToolParams) -> CLIResult:
    """Build and execute a ripgrep command.

    Args:
        computer: Computer instance to run the command on.
        params: Validated grep parameters.

    Returns:
        Raw CLIResult from ripgrep execution.

    Raises:
        CLIError: If the computer infrastructure fails.
    """
    command = build_rg_command(params)
    return await computer.run(command)


# ---------------------------------------------------------------------------
# Formatting helpers (used by GrepTool.execute)
# ---------------------------------------------------------------------------


def _paginate(lines: list[str], *, offset: int, limit: int) -> list[str]:
    """Apply offset/limit pagination to a list of lines.

    Args:
        lines: Lines to paginate.
        offset: Number of entries to skip from the start.
        limit: Maximum entries to return. 0 means unlimited.

    Returns:
        Paginated subset of lines.
    """
    if offset:
        lines = lines[offset:]
    if limit:
        lines = lines[:limit]
    return lines


# ---------------------------------------------------------------------------
# GrepTool - thin formatting layer
# ---------------------------------------------------------------------------


class GrepTool(BaseAgentTool[GrepToolParams]):
    """Tool for searching file contents using ripgrep.

    Wraps the ``rg`` binary to provide regex search across files.
    Supports three output modes: file paths, match content, and match
    counts.  Pagination (``offset`` / ``head_limit``) is applied
    client-side after ``rg`` returns results.

    Attributes:
        name: Tool name for API registration ("grep").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.

    Examples:
        ```python
        computer = LocalNativeComputer()
        tool = GrepTool(computer)
        result = await tool(pattern="TODO", path="/src")
        print(result.output)
        ```
    """

    name: Literal["grep"] = "grep"
    description: str = "A powerful search tool built on ripgrep."
    args_schema = GrepToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the GrepTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: GrepToolParams) -> ToolResult:
        """Search for a pattern in files.

        Delegates to ``run_ripgrep`` for command execution, then formats
        the raw ``CLIResult`` into a ``ToolResult``.

        Args:
            params: Validated parameters for the grep operation.

        Returns:
            ToolResult with search results based on output_mode.
        """
        try:
            result = await run_ripgrep(self._computer, params)
        except CLIError as exc:
            return ToolResult(
                error=str(exc),
                system=(
                    "This error did not come from your command. Your computer's"
                    " infrastructure has failed — this is never expected and"
                    " indicates a problem only the human developer can fix."
                    " Do not retry. Stop what you are doing and report this"
                    " failure to the user."
                ),
            )

        # Exit code >= 2 is a real error (invalid regex, permission denied, ...)
        if result.exit_code >= _RG_ERROR_EXIT_CODE:
            error = result.stderr or f"rg failed with exit code {result.exit_code}"
            return ToolResult(error=error)

        # Exit code 1 = no matches; also handle empty stdout with exit 0
        if result.exit_code == 1 or not result.stdout.strip():
            if params.output_mode == "files_with_matches":
                return ToolResult(output="No files found")
            if params.output_mode == "count":
                return ToolResult(
                    output="No matches found\n\nFound 0 total occurrences across 0 files.",
                )
            return ToolResult(output="No matches found")

        # Format based on output mode
        if params.output_mode == "files_with_matches":
            output = self._format_files(result.stdout, params)
        elif params.output_mode == "count":
            output = self._format_count(result.stdout, params)
        else:
            output = self._format_content(result.stdout, params)

        return ToolResult(output=output)

    # -- Formatters ----------------------------------------------------------

    @staticmethod
    def _format_files(stdout: str, params: GrepToolParams) -> str:
        """Format ``files_with_matches`` output with a summary header."""
        lines = [line for line in stdout.strip().splitlines() if line]
        lines = _paginate(lines, offset=params.offset, limit=params.head_limit)

        count = len(lines)
        header = f"Found {count} file{'s' if count != 1 else ''}"
        if params.head_limit or params.offset:
            header += f" limit: {params.head_limit}, offset: {params.offset}"

        if lines:
            return header + "\n" + "\n".join(lines)
        return header

    @staticmethod
    def _format_count(stdout: str, params: GrepToolParams) -> str:
        """Format ``count`` output with an occurrence summary."""
        lines = [line for line in stdout.strip().splitlines() if line]
        lines = _paginate(lines, offset=params.offset, limit=params.head_limit)

        total = 0
        for line in lines:
            # rg --count format: filepath:count
            file_part, _, count_part = line.rpartition(":")
            if file_part and count_part.strip().isdigit():
                total += int(count_part.strip())

        n_files = len(lines)
        summary = f"Found {total} total occurrence{'s' if total != 1 else ''} across {n_files} file{'s' if n_files != 1 else ''}."
        if params.head_limit or params.offset:
            summary += f" with pagination = limit: {params.head_limit}, offset: {params.offset}"

        if lines:
            return "\n".join(lines) + "\n\n" + summary
        return summary

    @staticmethod
    def _format_content(stdout: str, params: GrepToolParams) -> str:
        """Format ``content`` output with optional pagination."""
        lines = stdout.splitlines()
        lines = _paginate(lines, offset=params.offset, limit=params.head_limit)
        body = "\n".join(lines)
        if params.head_limit or params.offset:
            body += f"\n\nShowing results with pagination = limit: {params.head_limit}, offset: {params.offset}"
        return body
