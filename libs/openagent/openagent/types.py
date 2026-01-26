"""Shared data types for OpenAgent.

This module defines the core data structures used across the library,
particularly result types returned by tools and computer operations.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from openagent.computer.base import ExecutionMetadata


@dataclass(frozen=True, kw_only=True)
class ToolResult:
    r"""Base result type for tool execution.

    This is a generic result type that can represent output from any tool,
    including text output, errors, images, or system messages.

    Follows Anthropic's ToolResult pattern with support for combining results
    and boolean truthiness.

    Attributes:
        output: Standard output text from the tool.
        error: Error message if the operation failed.
        base64_image: Base64-encoded image data if tool produced an image.
        system: System-level messages or metadata.

    Examples:
        Basic usage:
        ```python
        result = ToolResult(output="hello")
        if result:  # True because output has a value
            print(result.output)
        ```

        Combining results:
        ```python
        r1 = ToolResult(output="line1\n")
        r2 = ToolResult(output="line2")
        combined = r1 + r2
        print(combined.output)  # "line1\nline2"
        ```

        Replacing fields:
        ```python
        result = ToolResult(output="hello")
        new_result = result.replace(error="something went wrong")
        ```
    """

    output: str | None = None
    error: str | None = None
    base64_image: str | None = None
    system: str | None = None

    def __bool__(self) -> bool:
        """Return True if any field has a value.

        This allows using ToolResult in boolean contexts to check if it
        contains any meaningful data.

        Returns:
            True if any field (output, error, base64_image, system) has a value.
        """
        return any(getattr(self, field.name) for field in fields(self))

    def __add__(self, other: ToolResult) -> ToolResult:
        r"""Combine two ToolResults by concatenating string fields.

        For string fields (output, error, system), concatenates values if both
        are present. For base64_image, raises ValueError if both have values
        (images cannot be concatenated).

        Args:
            other: Another ToolResult to combine with this one.

        Returns:
            A new ToolResult with combined fields.

        Raises:
            ValueError: If both results have base64_image values.

        Examples:
            ```python
            r1 = ToolResult(output="line1\n", error="err1")
            r2 = ToolResult(output="line2", error="err2")
            combined = r1 + r2
            # combined.output == "line1\nline2"
            # combined.error == "err1err2"
            ```
        """

        def combine_fields(
            field: str | None,
            other_field: str | None,
            *,
            concatenate: bool = True,
        ) -> str | None:
            if field and other_field:
                if concatenate:
                    return field + other_field
                msg = "Cannot combine tool results"
                raise ValueError(msg)
            return field or other_field

        return ToolResult(
            output=combine_fields(self.output, other.output),
            error=combine_fields(self.error, other.error),
            base64_image=combine_fields(
                self.base64_image,
                other.base64_image,
                concatenate=False,
            ),
            system=combine_fields(self.system, other.system),
        )

    def replace(self, **kwargs: str | None) -> ToolResult:
        """Create a new ToolResult with specified fields replaced.

        Args:
            **kwargs: Fields to replace (output, error, base64_image, system).

        Returns:
            A new ToolResult with the specified fields replaced.

        Examples:
            ```python
            result = ToolResult(output="hello")
            new_result = result.replace(error="something went wrong")
            # new_result.output == "hello"
            # new_result.error == "something went wrong"
            ```
        """
        return replace(self, **kwargs)

    def to_text(self) -> str:
        r"""Convert the result to a plain text string.

        Formats the result for consumption by LLMs or other text-based interfaces.
        Order: output first, then error (if any), then system (if any).

        Returns:
            A formatted string representation of the result.

        Examples:
            ```python
            result = ToolResult(output="hello")
            print(result.to_text())  # "hello"

            result = ToolResult(error="file not found")
            print(result.to_text())  # "<error>file not found</error>"

            result = ToolResult(output="partial", error="failed")
            # "partial\n<error>failed</error>"

            result = ToolResult(output="done", system="session restarted")
            # "done\n<system>session restarted</system>"
            ```
        """
        parts: list[str] = []
        if self.output:
            parts.append(self.output)
        if self.error:
            parts.append(f"<error>{self.error}</error>")
        if self.system:
            parts.append(f"\n<system-reminder>{self.system}</system-reminder>")
        return "\n".join(parts)


@dataclass(frozen=True, kw_only=True)
class CLIResult:
    """Result from CLI command execution.

    Contains the stdout, stderr, and exit code from a completed shell command.

    Attributes:
        stdout: Standard output from the command.
        stderr: Standard error from the command.
        exit_code: Process exit code. 0 typically indicates success.
        metadata: Execution metadata (duration, etc.).
    """

    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    metadata: ExecutionMetadata | None = None

    def to_text(self) -> str:
        """Convert the CLI result to a plain text string."""
        if self.exit_code == 0:
            parts: list[str] = []
            if self.stdout:
                parts.append(self.stdout)
            if self.stderr:
                parts.append(f"<stderr>{self.stderr}</stderr>")
            return "\n".join(parts) if parts else ""

        # Non-zero exit code: format as error
        error_parts: list[str] = [f"Exit Code {self.exit_code}"]
        if self.stderr:
            error_parts.append(self.stderr)
        if self.stdout:
            error_parts.append(f"\n{self.stdout}")
        error_content = "\n".join(error_parts)
        return f"<error>{error_content}</error>"


# Re-export CLIError for backward compatibility
from openagent.exceptions import CLIError as CLIError  # noqa: E402


# Tool Input Schemas
class BashToolParams(BaseModel):
    """Input schema for bash tool."""

    command: str = Field(description="Shell command to execute.")


class ReadToolParams(BaseModel):
    """Input schema for read tool."""

    file_path: str = Field(description="The absolute path to the file to read")
    offset: int = Field(
        default=0,
        ge=0,
        description="The line number to start reading from. Only provide if the file is too large to read at once",
    )
    limit: int = Field(
        default=2000,
        ge=1,
        description="The number of lines to read. Only provide if the file is too large to read at once.",
    )


class WriteToolParams(BaseModel):
    """Input schema for write tool."""

    file_path: str = Field(description="The absolute path to the file to write (must be absolute, not relative)")
    content: str = Field(description="The content to write to the file")


class EditToolParams(BaseModel):
    """Input schema for edit tool."""

    file_path: str = Field(description="The absolute path to the file to modify")
    old_string: str = Field(description="The text to replace")
    new_string: str = Field(description="The text to replace it with (must be different from old_string)")
    replace_all: bool = Field(default=False, description="Replace all occurences of old_string (default false)")


class LSToolParams(BaseModel):
    """Input schema for ls tool."""

    path: str = Field(default=".", description="Directory path to list")


class GlobToolParams(BaseModel):
    """Input schema for glob tool."""

    pattern: str = Field(description="The glob pattern to match files against")
    path: str | None = Field(
        default=None,
        description=(
            "The directory to search in. If not specified, the current working directory "
            "will be used. IMPORTANT: Omit this field to use the default directory. DO NOT "
            'enter "undefined" or "null" - simply omit it for the default behavior. Must be '
            "a valid directory path if provided."
        ),
    )


class GrepToolParams(BaseModel):
    """Input schema for grep tool."""

    model_config = ConfigDict(populate_by_name=True)

    pattern: str = Field(description="The regular expression pattern to search for in file contents")
    path: str = Field(
        default=".",
        description="File or directory to search in (rg PATH). Defaults to current working directory.",
    )
    glob: str | None = Field(
        default=None,
        description='Glob pattern to filter files (e.g. "*.js", "*.{ts,tsx}") - maps to rg --glob',
    )
    type: str | None = Field(
        default=None,
        description=(
            "File type to search (rg --type). Common types: js, py, rust, go, java, etc. More efficient than include for standard file types."
        ),
    )
    output_mode: Literal["content", "files_with_matches", "count"] = Field(
        default="files_with_matches",
        description=(
            'Output mode: "content" shows matching lines (supports -A/-B/-C context, -n line numbers, '
            'head_limit), "files_with_matches" shows file paths (supports head_limit), "count" shows '
            'match counts (supports head_limit). Defaults to "files_with_matches".'
        ),
    )
    case_insensitive: bool = Field(
        default=False,
        alias="-i",
        description="Case insensitive search (rg -i)",
    )
    show_line_numbers: bool = Field(
        default=True,
        alias="-n",
        description='Show line numbers in output (rg -n). Requires output_mode: "content", ignored otherwise. Defaults to true.',
    )
    after_context: int | None = Field(
        default=None,
        ge=0,
        alias="-A",
        description='Number of lines to show after each match (rg -A). Requires output_mode: "content", ignored otherwise.',
    )
    before_context: int | None = Field(
        default=None,
        ge=0,
        alias="-B",
        description='Number of lines to show before each match (rg -B). Requires output_mode: "content", ignored otherwise.',
    )
    context: int | None = Field(
        default=None,
        ge=0,
        alias="-C",
        description='Number of lines to show before and after each match (rg -C). Requires output_mode: "content", ignored otherwise.',
    )
    multiline: bool = Field(
        default=False,
        description="Enable multiline mode where . matches newlines and patterns can span lines (rg -U --multiline-dotall). Default: false.",
    )
    head_limit: int = Field(
        default=0,
        ge=0,
        description=(
            'Limit output to first N lines/entries, equivalent to "| head -N". Works across all '
            "output modes: content (limits output lines), files_with_matches (limits file paths), "
            "count (limits count entries). Defaults to 0 (unlimited)."
        ),
    )
    offset: int = Field(
        default=0,
        ge=0,
        description=(
            'Skip first N lines/entries before applying head_limit, equivalent to "| tail -n +N '
            '| head -N". Works across all output modes. Defaults to 0.'
        ),
    )
