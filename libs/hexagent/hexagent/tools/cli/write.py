"""Write tool for creating and overwriting files.

This module provides the WriteTool class that enables agents to write
content to files through a Computer interface.

The heavy lifting is done by :func:`run_write`, which builds a shell
command and delegates to ``computer.run()``.  ``WriteTool.execute`` is a
thin formatting layer that converts the resulting :class:`CLIResult` into
a :class:`ToolResult`.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Literal

from hexagent.exceptions import CLI_INFRA_ERROR_SYSTEM_REMINDER, CLIError
from hexagent.tools.base import BaseAgentTool
from hexagent.types import CLIResult, ToolResult, WriteToolParams

if TYPE_CHECKING:
    from hexagent.computer import Computer

# ---------------------------------------------------------------------------
# Python script executed on the (possibly remote) Computer.
#
# It receives a base64-encoded JSON payload containing "path" and "content"
# via a placeholder replaced at build time.  The script:
#   1. Checks whether the target file already exists and is non-empty.
#   2. Creates parent directories as needed.
#   3. Writes the content.
#   4. Prints a status message:
#      - "File created successfully at: <path>" for new files (or empty ones).
#      - "The file <path> has been updated. …" with a cat-n snippet for
#        overwrites of non-empty files.
#
# The marker ``BASE64_PLACEHOLDER`` is replaced by ``_build_write_command``
# with the actual base64 data.  Using ``.replace()`` instead of an f-string
# avoids the need to double-brace all Python braces in the template.
# ---------------------------------------------------------------------------

_WRITE_SCRIPT_TEMPLATE = """\
python3 <<'__WRITE_PYEOF__'
import base64, json, os, sys

data = json.loads(base64.b64decode("BASE64_PLACEHOLDER"))
path = data["path"]
content = data["content"]

try:
    existed = os.path.isfile(path) and os.path.getsize(path) > 0
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
except Exception as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(1)

if not existed:
    print("File created successfully at: " + path)
else:
    with open(path) as f:
        lines = f.readlines()
    numbered = ""
    for i, line in enumerate(lines, 1):
        numbered += "%6d\\t%s" % (i, line.rstrip("\\n")) + "\\n"
    print("The file " + path + " has been updated. Here's the result of running `cat -n` on a snippet of the edited file:")
    print(numbered, end="")
__WRITE_PYEOF__"""


def _build_write_command(file_path: str, content: str) -> str:
    """Build the shell command to write *content* to *file_path*.

    The content is JSON-serialised together with the path, base64-encoded,
    and embedded in a Python script delivered via a single-quoted heredoc.
    This guarantees that no shell interpretation occurs on the content
    regardless of what characters it contains.

    Args:
        file_path: Absolute path to the target file.
        content: The text content to write.

    Returns:
        A shell command string safe for ``computer.run()``.
    """
    payload = json.dumps({"path": file_path, "content": content})
    b64 = base64.b64encode(payload.encode()).decode()
    return _WRITE_SCRIPT_TEMPLATE.replace("BASE64_PLACEHOLDER", b64)


async def run_write(computer: Computer, file_path: str, content: str) -> CLIResult:
    """Write *content* to *file_path* on *computer*.

    Creates parent directories as needed.  Returns a :class:`CLIResult`
    whose *stdout* contains a human-readable status message on success,
    or whose *stderr* / *exit_code* describe the failure.

    Args:
        computer: The Computer to execute the write on.
        file_path: Absolute path to the target file.
        content: The text content to write.

    Returns:
        CLIResult with the outcome of the write operation.

    Raises:
        CLIError: If the computer infrastructure itself fails.
    """
    command = _build_write_command(file_path, content)
    return await computer.run(command)


class WriteTool(BaseAgentTool[WriteToolParams]):
    """Tool for writing content to files.

    Delegates the actual write to :func:`run_write` and converts the
    resulting :class:`CLIResult` into a :class:`ToolResult`.

    Attributes:
        name: Tool name for API registration.
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.

    Examples:
        Basic usage:
        ```python
        computer = LocalNativeComputer()
        tool = WriteTool(computer)
        result = await tool(file_path="/tmp/hello.txt", content="Hello!")
        print(result.output)  # "File created successfully at: /tmp/hello.txt"
        ```
    """

    name: Literal["Write"] = "Write"
    description: str = "Write content to a file. Creates parent directories as needed."
    args_schema = WriteToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the WriteTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: WriteToolParams) -> ToolResult:
        """Write content to a file.

        Args:
            params: Validated parameters containing file_path and content.

        Returns:
            ToolResult with output on success, or error on failure.
            Never both — output and error are mutually exclusive.
        """
        if not params.file_path.startswith("/"):
            return ToolResult(
                error=f"file_path must be an absolute path (starts with /), got: {params.file_path}",
            )

        try:
            result: CLIResult = await run_write(
                self._computer,
                params.file_path,
                params.content,
            )
        except CLIError as exc:
            return ToolResult(error=str(exc), system=CLI_INFRA_ERROR_SYSTEM_REMINDER)

        if result.exit_code == 0:
            parts = [p for p in (result.stdout, result.stderr) if p]
            return ToolResult(output="\n".join(parts) if parts else "")

        # Non-zero exit: exit code + stderr (tightly coupled), then stdout
        error = f"Exit code {result.exit_code}"
        if result.stderr:
            error += f"\n{result.stderr}"
        if result.stdout:
            error += f"\n\n{result.stdout}"
        return ToolResult(error=error)
