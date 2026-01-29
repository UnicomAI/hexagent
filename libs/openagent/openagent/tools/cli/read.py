"""Read tool for reading file contents.

This module provides the ReadTool class that enables agents to read
file contents with line numbers through a Computer interface.

Architecture:
    read_file() — standalone function with all heavy logic, returns CLIResult.
    ReadTool.execute() — thin formatting layer converting CLIResult → ToolResult.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Literal

from openagent.exceptions import CLIError
from openagent.tools.base import BaseAgentTool
from openagent.types import CLIResult, ReadToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer

_MAX_LINE_LENGTH = 2000
_LINE_SEPARATOR = "→"


async def read_file(
    computer: Computer,
    file_path: str,
    offset: int = 1,
    limit: int = 2000,
) -> CLIResult:
    """Read file contents with numbered lines.

    Args:
        computer: Computer to execute commands on.
        file_path: Path to the file to read.
        offset: Line number to start from (default 1). When offset=0, line
            numbering starts at 0. When offset>=1, line numbering starts at
            that value.
        limit: Maximum number of lines to return.

    Returns:
        CLIResult with numbered content in stdout on success,
        or error description in stderr with non-zero exit_code on failure.

    Raises:
        CLIError: Only for infrastructure failures (computer crashed, timeout).
    """
    quoted = shlex.quote(file_path)

    # Step 1: Validate — exists, not directory, regular file, readable, not binary.
    validate_cmd = (
        f"if [ ! -e {quoted} ]; then echo ENOENT; exit 1; "
        f"elif [ -d {quoted} ]; then echo EISDIR; exit 1; "
        f"elif [ ! -f {quoted} ]; then echo ENOTFILE; exit 1; "
        f"elif [ ! -r {quoted} ]; then echo EACCES; exit 1; "
        f"elif [ -s {quoted} ] && "
        f"file --mime-encoding -- {quoted} 2>/dev/null | grep -qw binary; "
        f"then echo BINARY; exit 1; "
        f"else echo OK; fi"
    )
    result = await computer.run(validate_cmd)

    if result.exit_code != 0:
        code = result.stdout.strip()
        errors: dict[str, str] = {
            "ENOENT": "File does not exist.",
            "EISDIR": "Illegal operation: path is a directory.",
            "ENOTFILE": "Illegal operation: path is not a file.",
            "EACCES": "Permission denied.",
            "BINARY": "Cannot display binary file.",
        }
        msg = errors.get(code, f"Cannot read file: {result.stderr}")
        return CLIResult(stderr=msg, exit_code=1)

    # Step 2: Read file and format with line numbers using Python.
    # Design: Split by '\n' to match Claude's native Read tool behavior,
    # which shows trailing empty lines when a file ends with newline(s).
    # offset=0 labels from 0; offset>=1 labels from that value.
    # start_idx is the 0-based index into the lines array.
    path_repr = repr(file_path)
    read_script = f"""
import sys
path = {path_repr}
offset = {offset}
limit = {limit}
sep = {_LINE_SEPARATOR!r}

with open(path) as f:
    content = f.read()

# Empty file: return nothing
if not content:
    sys.exit(0)

lines = content.split('\\n')
start_idx = max(0, offset - 1) if offset >= 1 else 0
start_label = offset
end_idx = start_idx + limit

window = lines[start_idx:end_idx]
if not window:
    sys.exit(0)

for i, line in enumerate(window):
    label = start_label + i
    print(f'{{label:6d}}{{sep}}{{line}}')
"""
    read_cmd = f"python3 -c {shlex.quote(read_script)}"
    result = await computer.run(read_cmd)

    if result.exit_code != 0:
        return CLIResult(
            stderr=result.stderr or "Failed to read file.",
            exit_code=result.exit_code,
        )

    # Step 3: Handle empty output (empty file or offset past end).
    if not result.stdout:
        if offset >= 1:
            # Count actual lines in file (empty file = 0, file with content = len(split))
            count_script = f"c=open({path_repr}).read(); print(0 if not c else len(c.split('\\n')))"
            count_result = await computer.run(f"python3 -c {shlex.quote(count_script)}")
            total_str = count_result.stdout.strip()
            total = int(total_str) if total_str.isdigit() else 0
            # Warn if offset exceeds available lines (including empty file case)
            if offset > total or total == 0:
                return CLIResult(
                    stderr=(f"Warning: the file exists but is shorter than the provided offset ({offset}). The file has {total} lines."),
                    exit_code=1,
                )
        return CLIResult(stdout="", exit_code=0)

    # Step 4: Truncate long lines.
    stdout = _truncate_long_lines(result.stdout)

    return CLIResult(
        stdout=stdout,
        stderr=result.stderr,
        exit_code=0,
        metadata=result.metadata,
    )


def _truncate_long_lines(content: str) -> str:
    """Truncate content portion of lines exceeding _MAX_LINE_LENGTH chars.

    Preserves the line number prefix (everything up to and including the
    separator arrow). Only the content after the arrow is measured and
    truncated.

    Args:
        content: Formatted output with line numbers.

    Returns:
        Content with long lines truncated.
    """
    if not content:
        return content

    lines = content.split("\n")
    truncated: list[str] = []
    for line in lines:
        sep_idx = line.find(_LINE_SEPARATOR)
        if sep_idx >= 0:
            prefix = line[: sep_idx + len(_LINE_SEPARATOR)]
            body = line[sep_idx + len(_LINE_SEPARATOR) :]
            if len(body) > _MAX_LINE_LENGTH:
                body = body[:_MAX_LINE_LENGTH]
            truncated.append(prefix + body)
        else:
            truncated.append(line)
    return "\n".join(truncated)


class ReadTool(BaseAgentTool[ReadToolParams]):
    r"""Tool for reading file contents with line numbers.

    Reads text files and returns content with numbered lines.

    Attributes:
        name: Tool name for API registration ("read").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.

    Examples:
        Basic usage:

        >>> computer = LocalNativeComputer()
        >>> tool = ReadTool(computer)
        >>> result = await tool(file_path="/etc/hosts")
        >>> print(result.output)
    """

    name: Literal["read"] = "read"
    description: str = "Read file contents with line numbers."
    args_schema = ReadToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the ReadTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: ReadToolParams) -> ToolResult:
        """Read a file's contents with line numbers.

        Args:
            params: Validated parameters containing file_path, offset, and limit.

        Returns:
            ToolResult with numbered file contents on success,
            or error message on failure. Output and error are mutually exclusive.
        """
        try:
            result: CLIResult = await read_file(
                self._computer,
                params.file_path,
                params.offset,
                params.limit,
            )
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

        if result.exit_code != 0:
            return ToolResult(error=result.stderr or f"Failed to read {params.file_path}")

        return ToolResult(output=result.stdout)
