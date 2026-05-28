"""PresentToUser tool for making files visible to the user.

This module provides the PresentToUserTool class that enables agents to
present files to the user for viewing and rendering in the client interface.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING, Literal

from hexagent.tools.base import BaseAgentTool
from hexagent.types import PresentToUserToolParams, ToolResult

if TYPE_CHECKING:
    from hexagent.computer.base import Computer

# Delimiter used to separate per-file result lines from the bash script.
# Chosen to be unlikely to appear in file paths or MIME types.
_DELIM = "@@PRESENT@@"

# Result prefixes emitted by the bash script.
_PREFIX_OK = "OK"
_PREFIX_COPIED = "COPIED"
_PREFIX_ERR = "ERR"

# ---------------------------------------------------------------------------
# Extension → MIME map (single source of truth)
#
# This dict covers types where ``file --mime-type`` returns a generic
# fallback (``text/plain`` or ``application/octet-stream``).  It is
# defined here in Python and auto-converted to a bash ``case`` block
# by ``_build_case_block()``, so there are zero system dependencies on
# the target machine and behaviour is deterministic across all platforms.
#
# ``file --mime-type`` remains the first pass — it handles binary magic-
# byte detection (PNG, PDF, JPEG, …) perfectly.  This map only kicks in
# when ``file`` can't be specific enough.
# ---------------------------------------------------------------------------
_EXT_MIME_MAP: dict[str, str] = {
    # -- Markup / docs --
    "md": "text/markdown",
    "markdown": "text/markdown",
    "rst": "text/x-rst",
    # -- Web --
    "css": "text/css",
    "js": "application/javascript",
    "mjs": "application/javascript",
    "ts": "application/typescript",
    "jsx": "text/jsx",
    "tsx": "text/tsx",
    # -- Programming --
    "py": "text/x-python",
    "rb": "text/x-ruby",
    "go": "text/x-go",
    "rs": "text/x-rust",
    "c": "text/x-c",
    "cpp": "text/x-c++",
    "h": "text/x-c",
    "hpp": "text/x-c++",
    "java": "text/x-java",
    "lua": "text/x-lua",
    "r": "text/x-r",
    "R": "text/x-r",
    "sh": "text/x-shellscript",
    "pl": "text/x-perl",
    "php": "text/x-php",
    "sql": "application/sql",
    # -- Config / data --
    "yaml": "application/x-yaml",
    "yml": "application/x-yaml",
    "toml": "application/toml",
    "ini": "text/x-ini",
    "cfg": "text/x-ini",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "env": "application/x-envoy",
    "log": "text/x-log",
    # -- Images --
    "bmp": "image/bmp",
    "ico": "image/x-icon",
    # -- Audio --
    "mp3": "audio/mpeg",
    "aac": "audio/aac",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    # -- Video --
    "webm": "video/webm",
    "mkv": "video/x-matroska",
    # -- Fonts --
    "ttf": "font/ttf",
    # -- Archives / packages --
    "zip": "application/zip",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "odt": "application/vnd.oasis.opendocument.text",
    # -- Database --
    "sqlite": "application/x-sqlite3",
    "sqlite3": "application/x-sqlite3",
    "db": "application/x-sqlite3",
    # -- Binary --
    "wasm": "application/wasm",
}


def _build_case_block() -> str:
    """Generate a bash ``case`` block from :data:`_EXT_MIME_MAP`.

    Groups extensions that share the same MIME type into a single
    ``ext1|ext2)`` arm for compact output.
    """
    # Invert: mime → sorted list of extensions
    mime_to_exts: dict[str, list[str]] = {}
    for ext, mime in _EXT_MIME_MAP.items():
        mime_to_exts.setdefault(mime, []).append(ext)

    arms: list[str] = []
    for mime, exts in mime_to_exts.items():
        pattern = "|".join(sorted(exts))
        arms.append(f'    {pattern}) echo "{mime}" ;;')

    arms.append('    *) echo "" ;;')
    return "\n".join(arms)


# The bash script body template.  ``{case_arms}`` is replaced at import
# time with the generated case block.  $1 is the output directory;
# $2.. are file paths.
_SCRIPT_BODY = r"""
OUTPUT_DIR="$1"; shift
mkdir -p "$OUTPUT_DIR"
REAL_OUT="$(realpath "$OUTPUT_DIR")"

_mime_by_ext() {{
  case "${{1##*.}}" in
{case_arms}
  esac
}}

D='@@PRESENT@@'

for fp in "$@"; do
  if [ ! -e "$fp" ]; then
    echo "ERR${{D}}Path does not exist: $fp"
  elif [ ! -f "$fp" ]; then
    echo "ERR${{D}}Path is not a file: $fp"
  else
    real="$(realpath "$fp")"
    mime="$(file --mime-type -b "$fp")"
    if [ "$mime" = "text/plain" ] || [ "$mime" = "application/octet-stream" ] || [ "$mime" = "application/zip" ]; then
      ext_mime="$(_mime_by_ext "$fp")"
      if [ -n "$ext_mime" ]; then
        mime="$ext_mime"
      fi
    fi
    case "$real" in
      "$REAL_OUT"/*)
        echo "OK${{D}}${{real}}${{D}}${{mime}}"
        ;;
      *)
        bname="$(basename "$fp")"
        dest="$OUTPUT_DIR/$bname"
        if [ -e "$dest" ]; then
          stem="${{bname%.*}}"
          ext="${{bname##*.}}"
          if [ "$stem" = "$bname" ]; then
            ext=""
          else
            ext=".$ext"
          fi
          counter=1
          while [ -e "$dest" ]; do
            dest="$OUTPUT_DIR/${{stem}}_${{counter}}${{ext}}"
            counter=$((counter + 1))
          done
        fi
        cp -p "$fp" "$dest"
        echo "COPIED${{D}}${{dest}}${{D}}${{mime}}${{D}}${{fp}}"
        ;;
    esac
  fi
done
""".format(case_arms=_build_case_block())  # noqa: UP032 — can't use f-string; bash ${} conflicts

# WSL/bash is sensitive to CRLF in inline scripts (can break function
# definitions/quoting with opaque parse errors). Normalize to LF at runtime so
# behavior is stable regardless of host checkout EOL settings.
_SCRIPT_BODY_LF = _SCRIPT_BODY.replace("\r\n", "\n").replace("\r", "\n")


def _build_command(filepaths: list[str], output_dir: str) -> str:
    """Build a bash command that processes all file paths.

    The script body is constant-size.  File paths and the output directory
    are passed as shell arguments, keeping the command length proportional
    only to the paths themselves.

    Args:
        filepaths: Paths to present.
        output_dir: Directory where files are made available.

    Returns:
        A shell command string safe for ``Computer.run()``.
    """
    quoted_args = " ".join(shlex.quote(p) for p in [output_dir, *filepaths])
    return f"bash -c {shlex.quote(_SCRIPT_BODY_LF)} _ {quoted_args}"


class PresentToUserTool(BaseAgentTool[PresentToUserToolParams]):
    """Tool for presenting files to the user.

    Makes files visible to the user for viewing, downloading, or
    interacting with in the client interface. Uses a single bash
    invocation on the Computer to validate paths, copy files into the
    output directory, and detect MIME types.

    Attributes:
        name: Tool name for API registration.
        description: Tool description for LLM.
        args_schema: Pydantic model for input validation.
    """

    name: Literal["PresentToUser"] = "PresentToUser"
    description: str = (
        "Makes files visible to the user for viewing and rendering in the "
        "client interface. Accepts an array of file paths and returns output "
        "paths where files can be accessed. The first file path should "
        "correspond to the file most relevant for the user to see first."
    )
    args_schema = PresentToUserToolParams

    def __init__(self, *, computer: Computer, output_dir: str) -> None:
        """Initialize the PresentToUserTool.

        Args:
            computer: The computer instance for filesystem access.
            output_dir: Directory where presented files are made available.
        """
        self._computer = computer
        self._output_dir = output_dir

    async def execute(self, params: PresentToUserToolParams) -> ToolResult:
        """Present files to the user.

        Runs a single bash command on the Computer to validate all paths,
        copy files not already in the output directory, and detect
        MIME types. If any path is invalid, the entire call fails.

        Args:
            params: Validated parameters containing file paths to present.

        Returns:
            ToolResult with XML-formatted file info on success,
            or error details on failure.
        """
        command = _build_command(params.filepaths, self._output_dir)
        cli_result = await self._computer.run(command)

        if cli_result.exit_code != 0:
            error = cli_result.stderr or cli_result.stdout or "Unknown error"
            return ToolResult(error=error)

        return _parse_output(cli_result.stdout)


def _parse_output(stdout: str) -> ToolResult:
    """Parse structured output lines from the bash script into a ToolResult."""
    errors: list[str] = []
    file_blocks: list[str] = []
    copied_lines: list[str] = []

    for line in stdout.strip().splitlines():
        parts = line.split(_DELIM)
        tag = parts[0]

        if tag == _PREFIX_ERR:
            errors.append(parts[1])
        elif tag == _PREFIX_OK:
            output_path, mime_type = parts[1], parts[2]
            file_blocks.append(f"<file>\n<file_path>{output_path}</file_path>\n<mime_type>{mime_type}</mime_type>\n</file>")
        elif tag == _PREFIX_COPIED:
            output_path, mime_type, original = parts[1], parts[2], parts[3]
            file_blocks.append(f"<file>\n<file_path>{output_path}</file_path>\n<mime_type>{mime_type}</mime_type>\n</file>")
            copied_lines.append(f"Copied {original} to {output_path}")

    if errors:
        return ToolResult(error="\n".join(errors))

    output = "\n".join(file_blocks)
    if copied_lines:
        output += "\nFiles copied:\n" + "\n".join(copied_lines)

    return ToolResult(output=output)
