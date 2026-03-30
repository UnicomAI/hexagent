"""Glob tool for finding files by pattern.

This module provides the GlobTool class that enables agents to find
files matching glob patterns through a Computer interface.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Literal

from hexagent.exceptions import CLI_INFRA_ERROR_SYSTEM_REMINDER, CLIError
from hexagent.tools.base import BaseAgentTool
from hexagent.types import CLIResult, GlobToolParams, ToolResult

if TYPE_CHECKING:
    from hexagent.computer import Computer

_MAX_RESULTS = 100

# Python script executed on the computer to perform glob matching.
#
# Design choice: python3 is used because it cleanly handles brace expansion
# ({py,toml}), recursive matching, mtime sorting, and is portable across
# Linux and macOS (unlike find+stat where stat flags differ per OS).
#
# Args (via sys.argv): [1]=search_dir, [2]=pattern, [3]=result_limit
# Exit 0: success (stdout = newline-separated absolute paths; empty = no matches)
# Exit 2: search directory does not exist (stderr = error message)
_GLOB_SCRIPT = """\
import pathlib, re, sys
def expand_braces(pat):
    m = re.search(r"\\{([^{}]+)\\}", pat)
    if not m:
        return [pat]
    pre, suf = pat[:m.start()], pat[m.end():]
    return [x for o in m.group(1).split(",") for x in expand_braces(pre + o + suf)]
d = pathlib.Path(sys.argv[1]).resolve()
if not d.is_dir():
    print("Directory does not exist: " + sys.argv[1], file=sys.stderr)
    sys.exit(2)
limit = int(sys.argv[3])
pats = expand_braces(sys.argv[2])
pats = [("**/" + p if "**" not in p else p) for p in pats]
seen = set()
files = []
for p in pats:
    for f in d.glob(p):
        s = str(f)
        if s not in seen:
            seen.add(s)
            try:
                mt = f.stat().st_mtime
            except OSError:
                mt = 0
            files.append((s, mt))
files.sort(key=lambda x: x[1])
for path, _ in files[:limit]:
    print(path)
"""


async def run_glob(
    computer: Computer,
    pattern: str,
    path: str | None,
) -> CLIResult:
    """Execute a glob pattern search on the computer.

    Builds a Python script that finds files matching the given glob pattern,
    sorted by modification time (most recent first), and runs it via the
    computer.

    Args:
        computer: Computer to execute the glob command on.
        pattern: Glob pattern (supports ``**``, ``*``, ``?``, and ``{a,b}``
            brace expansion). Patterns without ``**`` are automatically made
            recursive.
        path: Directory to search in, or None to use cwd.

    Returns:
        CLIResult where:

        - exit_code 0 with stdout: matching paths (one per line)
        - exit_code 0 with empty stdout: no matches
        - exit_code 2 with stderr: directory does not exist
    """
    search_dir = path if path is not None else "."
    command = f"python3 - {shlex.quote(search_dir)} {shlex.quote(pattern)} {_MAX_RESULTS} <<'PYGLOB'\n{_GLOB_SCRIPT}PYGLOB"
    return await computer.run(command)


class GlobTool(BaseAgentTool[GlobToolParams]):
    r"""Tool for finding files by pattern.

    Uses python3's pathlib.glob() on the Computer to find files matching
    glob patterns. Results are sorted by modification time (most recent
    first) and limited to 100 entries.

    Attributes:
        name: Tool name for API registration.
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["Glob"] = "Glob"
    description: str = "Find files matching a glob pattern. Max 100 results."
    args_schema = GlobToolParams

    def __init__(self, computer: Computer) -> None:
        """Initialize the GlobTool.

        Args:
            computer: The Computer instance to execute commands on.
        """
        self._computer = computer

    async def execute(self, params: GlobToolParams) -> ToolResult:
        """Find files matching a glob pattern, sorted by modification time.

        Args:
            params: Validated parameters containing pattern and path.

        Returns:
            ToolResult with matching file paths sorted by mtime (oldest first),
            one per line.
        """
        try:
            result: CLIResult = await run_glob(self._computer, params.pattern, params.path)
        except CLIError as exc:
            return ToolResult(error=str(exc), system=CLI_INFRA_ERROR_SYSTEM_REMINDER)

        if result.exit_code != 0:
            return ToolResult(error=result.stderr or f"Glob failed (exit {result.exit_code})")

        if not result.stdout:
            return ToolResult(output="No files found")

        return ToolResult(output=result.stdout)
