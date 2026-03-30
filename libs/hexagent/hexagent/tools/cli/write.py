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
import shlex
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

_WRITE_SCRIPT_TEMPLATE = r"""
import sys, base64, json, os
try:
    # Read base64 payload from stdin to avoid command line length limits (WinError 206)
    raw_payload = sys.stdin.read().strip()
    if not raw_payload:
        print("ERR@@WRITE@@Empty payload received via stdin")
        sys.exit(1)
    payload = json.loads(base64.b64decode(raw_payload).decode('utf-8'))
    path = payload['path']
    content = payload['content']
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("OK@@WRITE@@File written successfully")
except Exception as e:
    print(f"ERR@@WRITE@@{str(e)}")
    sys.exit(1)
"""


class WriteTool(BaseAgentTool[WriteToolParams]):
    """Tool for writing content to a file."""

    name: Literal["Write"] = "Write"
    description: str = "Write content to a file. Overwrites if exists."
    args_schema = WriteToolParams

    async def execute(self, params: WriteToolParams) -> ToolResult:
        """Execute the write operation."""
        # Check if we are in a session to resolve paths
        computer = self.context.get("computer")
        if not computer:
            return ToolResult(error="No computer session active")

        # Build payload
        payload = json.dumps({"path": params.file_path, "content": params.content})
        b64_payload = base64.b64encode(payload.encode("utf-8")).decode("utf-8")

        # Execute via python script on the guest, passing payload via stdin
        cmd = f"python3 -c {shlex.quote(_WRITE_SCRIPT_TEMPLATE)}"
        result = await computer.run(cmd, input=b64_payload)

        if result.exit_code != 0:
            return ToolResult(error=result.stderr or result.stdout or "Unknown error during write")

        output = result.stdout.strip()
        if output.startswith("OK@@WRITE@@"):
            return ToolResult(output=output.removeprefix("OK@@WRITE@@"))
        if output.startswith("ERR@@WRITE@@"):
            return ToolResult(error=output.removeprefix("ERR@@WRITE@@"))

        return ToolResult(error=f"Unexpected output from write script: {output}")
