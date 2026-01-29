"""Edit tool for performing string replacements in files.

This module provides the EditTool class that enables agents to perform
exact string replacements in files through a Computer interface.

Architecture:
    edit_file() — implementation function, returns CLIResult
    EditTool.execute() — thin formatting layer, converts CLIResult → ToolResult

File I/O is performed on the target computer via ``python3 -c``.
Parameters are JSON-encoded then base64-encoded to avoid shell escaping issues.
"""

from __future__ import annotations

import base64
import json
import shlex
from typing import TYPE_CHECKING, Literal

from openagent.exceptions import CLI_INFRA_ERROR_SYSTEM_REMINDER, CLIError
from openagent.tools.base import BaseAgentTool
from openagent.types import CLIResult, EditToolParams, ToolResult

if TYPE_CHECKING:
    from openagent.computer import Computer

# ---------------------------------------------------------------------------
# Python script executed on the target computer.
#
# Receives a base64-encoded JSON payload as sys.argv[1] with keys:
#   fp  — file path
#   old — old string to find
#   new — replacement string
#   all — whether to replace all occurrences
#
# On success: prints message to stdout, exits 0.
# On error:   prints message to stderr, exits 1.
# ---------------------------------------------------------------------------
_EDIT_SCRIPT = r"""
import base64, json, sys

params = json.loads(base64.b64decode(sys.argv[1]))
fp = params["fp"]
old = params["old"]
new = params["new"]
all_ = params["all"]

if not old:
    print("old_string must not be empty.", file=sys.stderr)
    sys.exit(1)

if old == new:
    print("No changes to make: old_string and new_string are exactly the same.", file=sys.stderr)
    sys.exit(1)

try:
    with open(fp) as f:
        content = f.read()
except FileNotFoundError:
    import os
    print("File does not exist. Current working directory: " + os.getcwd(), file=sys.stderr)
    sys.exit(1)
except PermissionError:
    print("Permission denied: " + fp, file=sys.stderr)
    sys.exit(1)
except IsADirectoryError:
    print("Is a directory, not a file: " + fp, file=sys.stderr)
    sys.exit(1)

count = content.count(old)

if count == 0:
    print("String to replace not found in file.\nString: " + old, file=sys.stderr)
    sys.exit(1)

if not all_ and count > 1:
    print(
        "Found " + str(count) + " matches of the string to replace, but replace_all"
        " is false. To replace all occurrences, set replace_all to true. To replace"
        " only one occurrence, please provide more context to uniquely identify the"
        " instance.\nString: " + old,
        file=sys.stderr,
    )
    sys.exit(1)

if all_:
    result = content.replace(old, new)
else:
    result = content.replace(old, new, 1)

try:
    with open(fp, "w") as f:
        f.write(result)
except PermissionError:
    print("Permission denied: cannot write to " + fp, file=sys.stderr)
    sys.exit(1)

if all_:
    print("The file " + fp + " has been updated. All occurrences of '" + old + "' were successfully replaced with '" + new + "'.")
else:
    print("The file " + fp + " has been updated successfully.")
""".strip()


async def edit_file(
    computer: Computer,
    file_path: str,
    old_string: str,
    new_string: str,
    *,
    replace_all: bool = False,
) -> CLIResult:
    """Perform exact string replacement in a file via the computer.

    Builds a ``python3 -c`` command with base64-encoded parameters and
    executes it on the target computer.

    Args:
        computer: Computer to execute commands on.
        file_path: Absolute path to the file to modify.
        old_string: Exact text to find.
        new_string: Replacement text.
        replace_all: If True, replace all occurrences. If False,
            ``old_string`` must appear exactly once.

    Returns:
        CLIResult with success message in stdout (exit 0) or error
        in stderr (exit 1).

    Raises:
        CLIError: If the computer infrastructure fails (timeout, crash).
    """
    payload = json.dumps(
        {
            "fp": file_path,
            "old": old_string,
            "new": new_string,
            "all": replace_all,
        }
    )
    encoded = base64.b64encode(payload.encode()).decode()
    command = f"python3 -c {shlex.quote(_EDIT_SCRIPT)} {encoded}"
    return await computer.run(command)


class EditTool(BaseAgentTool[EditToolParams]):
    """Tool for performing string replacements in files.

    Performs exact (literal) string matching and replacement. No regex.
    When ``replace_all`` is ``False``, the ``old_string`` must appear
    exactly once in the file; otherwise an error is returned.

    Attributes:
        name: Tool name for API registration ("edit").
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.

    Examples:
        Basic usage:
        ```python
        computer = LocalNativeComputer()
        tool = EditTool(computer)
        result = await tool(
            file_path="/tmp/example.txt",
            old_string="hello",
            new_string="world",
        )
        print(result.output)  # "The file /tmp/example.txt has been updated successfully."
        ```
    """

    name: Literal["edit"] = "edit"
    description: str = "Perform exact string replacement in a file."
    args_schema = EditToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the EditTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: EditToolParams) -> ToolResult:
        """Replace a string in a file.

        Args:
            params: Validated parameters containing file_path, old_string,
                new_string, and replace_all flag.

        Returns:
            ToolResult with output on success, or error on failure.
            Never both—output and error are mutually exclusive.
        """
        try:
            result: CLIResult = await edit_file(
                self._computer,
                params.file_path,
                params.old_string,
                params.new_string,
                replace_all=params.replace_all,
            )
        except CLIError as exc:
            return ToolResult(error=str(exc), system=CLI_INFRA_ERROR_SYSTEM_REMINDER)

        if result.exit_code == 0:
            return ToolResult(output=result.stdout or "")

        return ToolResult(error=result.stderr or f"Edit failed (exit code {result.exit_code})")
