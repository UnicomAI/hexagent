"""Shared data types for HexAgent.

This module defines the core data structures used across the library,
particularly result types returned by tools and computer operations.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, fields, replace
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal, NotRequired, Protocol, TypedDict, runtime_checkable

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from datetime import datetime

    from hexagent.computer.base import ExecutionMetadata
    from hexagent.harness.definition import AgentDefinition
    from hexagent.harness.model import ModelProfile
    from hexagent.mcp import McpClient
    from hexagent.tools.base import BaseAgentTool


class CompactionPhase(str, Enum):
    """State machine phases for context compaction.

    The compaction process spans 3 iterations through the agent loop:

    1. NONE -> REQUESTING: Token count exceeds threshold, request a summary.
    2. REQUESTING -> APPLYING: LLM generated a summary, apply it.
    3. APPLYING -> NONE: Rebuild messages with summary, resume normal operation.
    """

    NONE = "none"
    REQUESTING = "requesting"
    APPLYING = "applying"


# ---------------------------------------------------------------------------
# Image content types for multimodal tool results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Base64Source:
    """Base64-encoded binary content.

    Attributes:
        data: Base64-encoded bytes.
        media_type: MIME type (e.g. ``"image/png"``).
    """

    data: str
    media_type: str


@dataclass(frozen=True)
class UrlSource:
    """Content referenced by URL.

    Attributes:
        url: HTTP(S) URL pointing to the content.
    """

    url: str


ImageContent = Base64Source | UrlSource
"""An image in a tool result, sourced as base64 data or a URL."""


@dataclass(frozen=True, kw_only=True)
class ToolResult:
    r"""Base result type for tool execution.

    This is a generic result type that can represent output from any tool,
    including text output, error, images, or system message.

    Follows Anthropic's ToolResult pattern with support for combining results
    and boolean truthiness.

    Attributes:
        output: The text output from the tool.
        error: Error message if the tool execution failed.
        images: Images produced by the tool (base64 or URL).
        system: System-level message or metadata for the agent.

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

        With images:
        ```python
        result = ToolResult(
            output="Screenshot captured",
            images=(Base64Source(data="iVBOR...", media_type="image/png"),),
        )
        ```
    """

    output: str | None = None
    error: str | None = None
    images: tuple[ImageContent, ...] = ()
    system: str | None = None

    def __bool__(self) -> bool:
        """Return True if any field has a value.

        This allows using ToolResult in boolean contexts to check if it
        contains any meaningful data.

        Returns:
            True if any field (output, error, images, system) has a value.
        """
        return any(getattr(self, f.name) for f in fields(self))

    def __add__(self, other: ToolResult) -> ToolResult:
        r"""Combine two ToolResults by concatenating their fields.

        For string fields (output, error, system), concatenates values if both
        are present. For images, concatenates tuples.

        Args:
            other: Another ToolResult to combine with this one.

        Returns:
            A new ToolResult with combined fields.

        Examples:
            ```python
            r1 = ToolResult(output="line1\n", error="err1")
            r2 = ToolResult(output="line2", error="err2")
            combined = r1 + r2
            # combined.output == "line1\nline2"
            # combined.error == "err1err2"
            ```
        """

        def combine_str(
            val: str | None,
            other_val: str | None,
        ) -> str | None:
            if val and other_val:
                return val + other_val
            return val or other_val

        return ToolResult(
            output=combine_str(self.output, other.output),
            error=combine_str(self.error, other.error),
            images=self.images + other.images,
            system=combine_str(self.system, other.system),
        )

    def replace(self, **kwargs: Any) -> ToolResult:
        """Create a new ToolResult with specified fields replaced.

        Args:
            **kwargs: Fields to replace (output, error, images, system).

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

    def __str__(self) -> str:
        """Return the text representation of this result."""
        return self.to_text()

    def to_text(self) -> str:
        r"""Convert the result to a plain text string.

        Formats the result for consumption by LLMs or other text-based interfaces.

        - Output comes first, error on the next line if both present.
        - If neither output nor error exists, a default system notice is emitted.
          Any existing system message is appended on the next line.
        - If output/error *and* system are present, system is separated by a
          blank line.

        Returns:
            A formatted string representation of the result.

        Examples:
            ```python
            ToolResult(output="hello").to_text()
            # "hello"

            ToolResult(error="file not found").to_text()
            # "<error>file not found</error>"

            ToolResult(output="partial", error="failed").to_text()
            # "partial\n<error>failed</error>"

            ToolResult(output="done", system="session restarted").to_text()
            # "done\n\n<system>session restarted</system>"

            ToolResult().to_text()
            # "<system>Tool ran without output or errors</system>"

            ToolResult(system="session restarted").to_text()
            # "<system>Tool ran without output or errors\nsession restarted</system>"
            ```
        """
        parts: list[str] = []
        if self.output:
            parts.append(self.output)
        if self.error:
            parts.append(f"<error>{self.error}</error>")

        content = "\n".join(parts)

        if not content:
            system_msg = "Tool ran without output or errors"
            if self.system:
                system_msg += f"\n{self.system}"
            return f"<system>{system_msg}</system>"

        if self.system:
            return f"{content}\n\n<system>{self.system}</system>"

        return content

    def to_content_blocks(
        self,
        format: Literal["anthropic", "openai"] = "openai",  # noqa: A002
    ) -> list[dict[str, Any]]:
        """Convert the result to structured content blocks.

        Always returns a list of typed content block dicts — even for
        text-only results.  The ``format`` parameter selects the wire
        format:

        - ``"anthropic"`` — native Anthropic Messages API structure
          (``text`` and ``image`` blocks with ``source``).
        - ``"openai"`` — OpenAI Chat Completions structure
          (``text`` and ``image_url`` blocks with data-URI encoding).

        Args:
            format: Content block wire format.

        Returns:
            A list of content block dicts.
        """
        if format == "anthropic":
            return self._to_anthropic_content_blocks()
        if format == "openai":
            return self._to_openai_content_blocks()
        msg = f"Unsupported content block format: {format!r}"
        raise ValueError(msg)

    def _to_anthropic_content_blocks(self) -> list[dict[str, Any]]:
        """Format as Anthropic-native content blocks.

        Returns ``{"type": "text", "text": ...}`` for text and
        ``{"type": "image", "source": {...}}`` for images — matching
        the Anthropic Messages API structure directly.
        """
        blocks: list[dict[str, Any]] = []

        text = self.to_text()
        if text:
            blocks.append({"type": "text", "text": text})

        for img in self.images:
            if isinstance(img, Base64Source):
                blocks.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img.media_type,
                            "data": img.data,
                        },
                    }
                )
            elif isinstance(img, UrlSource):
                blocks.append(
                    {
                        "type": "image",
                        "source": {"type": "url", "url": img.url},
                    }
                )

        return blocks

    def _to_openai_content_blocks(self) -> list[dict[str, Any]]:
        """Format as OpenAI-style content blocks.

        Returns ``{"type": "text", ...}`` and optionally
        ``{"type": "image_url", ...}`` dicts.  The ``image_url`` format
        uses data-URIs for base64 sources.
        """
        blocks: list[dict[str, Any]] = []

        text = self.to_text()
        if text:
            blocks.append({"type": "text", "text": text})

        for img in self.images:
            if isinstance(img, Base64Source):
                blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{img.media_type};base64,{img.data}"},
                    }
                )
            elif isinstance(img, UrlSource):
                blocks.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": img.url},
                    }
                )

        return blocks


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


# Tool Input Schemas
class BashToolParams(BaseModel):
    """Input schema for bash tool."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        description=(
            "Clear, concise description of what this command does in active voice."
            ' Never use words like "complex" or "risk" in the description'
            " - just describe what it does. (Always generate this param first)"
        ),
    )
    command: str = Field(description="Shell command to execute.")
    run_in_background: bool = Field(
        default=False,
        description="Set to true to run this command in the background. Use TaskOutput to read the output later.",
    )
    timeout: int | None = Field(
        default=None,
        ge=0,
        description="Optional timeout in milliseconds (max 600000).",
    )


class ReadToolParams(BaseModel):
    """Input schema for read tool."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this Read does in active voice. (Always generate this param first)",
    )
    file_path: str = Field(description="The absolute path to the file to read")
    offset: int = Field(
        default=1,
        ge=0,
        description="The line number to start reading from. Only provide if the file is too large to read at once.",
    )
    limit: int = Field(
        default=2000,
        ge=1,
        description="The number of lines to read. Only provide if the file is too large to read at once.",
    )


class WriteToolParams(BaseModel):
    """Input schema for write tool."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this Write does in active voice. (Always generate this param first)",
    )
    file_path: str = Field(
        validation_alias=AliasChoices("file_path", "path"),
        description="The absolute path to the target file to write (must be absolute, not relative)",
    )
    content: str = Field(description="The content to write to the file")


class EditToolParams(BaseModel):
    """Input schema for edit tool."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this Edit does in active voice. (Always generate this param first)",
    )
    file_path: str = Field(
        validation_alias=AliasChoices("file_path", "path"),
        description="The absolute path to the file to modify",
    )
    old_string: str = Field(description="The text to replace")
    new_string: str = Field(description="The text to replace it with (must be different from old_string)")
    replace_all: bool = Field(default=False, description="Replace all occurences of old_string (default false)")


class GlobToolParams(BaseModel):
    """Input schema for glob tool."""

    model_config = ConfigDict(extra="forbid")

    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this Glob does in active voice. (Always generate this param first)",
    )
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

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this Grep does in active voice. (Always generate this param first)",
    )
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


class WebSearchToolParams(BaseModel):
    """Input schema for web search tool."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(description="The search query to use")


class WebFetchToolParams(BaseModel):
    """Input schema for web fetch tool."""

    model_config = ConfigDict(extra="forbid")

    url: str = Field(description="URL of the web page to fetch and extract content from")
    prompt: str | None = Field(
        default=None,
        description="Optional question to answer about the page content. When provided, returns a focused answer instead of the full page.",
    )


class SkillToolParams(BaseModel):
    """Input schema for skill tool."""

    model_config = ConfigDict(extra="forbid")

    skill: str = Field(description="The skill name to invoke (e.g., 'commit', 'review-pr', 'pdf')")
    args: str | None = Field(default=None, description="Optional arguments for the skill")


class AgentToolParams(BaseModel):
    """Input schema for the Agent tool."""

    model_config = ConfigDict(extra="forbid")

    description: str = Field(description="Clear, concise 3-8 words description of the task (Always generate this param first)")
    prompt: str = Field(description="The task for the agent to perform")
    subagent_type: str = Field(
        default="general-purpose",
        description="The type of specialized agent to use for this task",
    )
    resume: str | None = Field(
        default=None,
        description="Optional agent ID to resume from. Continues the previous agent's conversation.",
    )
    run_in_background: bool = Field(
        default=False,
        description="Set to true to run this agent in the background. Use TaskOutput to read the output later.",
    )


class TaskOutputToolParams(BaseModel):
    """Input schema for the TaskOutput tool."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(description="The task ID to get output from")
    block: bool = Field(default=True, description="Whether to wait for completion")
    timeout: int = Field(
        default=30000,
        ge=0,
        le=600000,
        description="Max wait time in ms",
    )


class TaskStopToolParams(BaseModel):
    """Input schema for the TaskStop tool."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(description="The task ID to cancel")


class TodoItem(BaseModel):
    """A single todo item."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    content: str = Field(min_length=1, description="The todo item content")
    status: Literal["pending", "in_progress", "completed"] = Field(
        description="The status of the todo item",
    )
    active_form: str = Field(
        min_length=1,
        validation_alias=AliasChoices("active_form", "activeForm"),
        description="The active form of the todo item",
    )


class TodoWriteToolParams(BaseModel):
    """Input schema for the TodoWrite tool."""

    model_config = ConfigDict(extra="forbid")

    todos: list[TodoItem] = Field(description="The updated todo list")


class PresentToUserToolParams(BaseModel):
    """Input schema for the PresentFiles tool."""

    model_config = ConfigDict(extra="forbid")

    filepaths: list[str] = Field(
        min_length=1,
        description="Array of file paths identifying which files to present to the user",
    )


# Runtime Types


@dataclass(frozen=True)
class SubagentResult:
    """Result returned by a :class:`SubagentRunner` after executing a subagent.

    Attributes:
        output: The text output produced by the subagent.
        messages: Full message history from the subagent conversation.
    """

    output: str
    messages: list[Any]


@runtime_checkable
class SubagentRunner(Protocol):
    """Protocol for executing subagents.

    Any object that implements :meth:`get_definition` and :meth:`run`
    can serve as a runner for the Agent tool.  The concrete
    LangChain-based implementation lives in
    :class:`~hexagent.langchain.subagent.LangChainSubagentRunner`.
    """

    def get_definition(self, subagent_type: str) -> AgentDefinition | None:
        """Look up an agent definition by type name."""
        ...

    async def run(
        self,
        definition: AgentDefinition | None,
        prompt: str,
        prior_messages: list[Any] | None = None,
        *,
        task_id: str = "",
    ) -> SubagentResult:
        """Execute a subagent and return its result.

        Args:
            definition: Agent type spec, or ``None`` for general-purpose.
            prompt: The task prompt for the subagent.
            prior_messages: Conversation history for resume.
            task_id: Unique task identifier.

        Returns:
            SubagentResult with output text and full message history.
        """
        ...


class CompletionModel:
    """Framework-agnostic LLM invocation wrapper.

    Bundles an async completion function with its input capacity,
    allowing tools to invoke an LLM without depending on any
    specific framework.

    Attributes:
        max_input_chars: Maximum characters the model can accept as input.

    Examples:
        ```python
        async def my_complete(system: str, user: str) -> str:
            return "response"


        model = CompletionModel(my_complete, max_input_chars=300_000)
        result = await model.complete(system="You are helpful.", user="Hello")
        ```
    """

    def __init__(
        self,
        fn: Callable[[str, str], Awaitable[str]],
        *,
        max_input_chars: int,
    ) -> None:
        """Create a CompletionModel.

        Args:
            fn: Async function ``(system, user) -> response`` that invokes the LLM.
            max_input_chars: Maximum characters the model can accept as input.
        """
        self._fn = fn
        self.max_input_chars = max_input_chars

    async def complete(self, *, system: str, user: str) -> str:
        """Invoke the LLM with system and user messages.

        Args:
            system: System instruction for the model.
            user: User message / prompt.

        Returns:
            The model's response as a string.
        """
        return await self._fn(system, user)


@dataclass(frozen=True)
class Skill:
    """A skill capability.

    Skills are specialized capabilities that provide domain-specific
    knowledge and behaviors to the agent.

    Attributes:
        name: Unique identifier for the skill.
        description: Human-readable description for prompt assembly.
        path: Filesystem path to the skill directory on the computer.
    """

    name: str
    description: str
    path: str


@runtime_checkable
class SkillCatalog(Protocol):
    """Minimal interface for checking skill availability.

    Abstracts the mechanism by which skills are discovered, so that
    consumers (e.g. SkillTool) depend on the capability, not on a
    concrete resolver implementation.
    """

    async def has(self, name: str) -> bool:
        """Return True if *name* is a known skill, re-discovering if needed."""
        ...


ApprovalCallback = Callable[
    [str, dict[str, Any], str | None],
    Awaitable[bool],
]
"""Callback for human-in-the-loop approval.

Signature: ``(tool_name, tool_args, approval_prompt) -> approved``.
"""


@dataclass(frozen=True)
class EnvironmentContext:
    """Detected runtime environment properties.

    Populated by :class:`~hexagent.harness.environment.EnvironmentResolver`
    via shell commands on the Computer.

    Attributes:
        working_dir: Current working directory.
        is_git_repo: Whether the working directory is inside a git repository.
        platform: Lowercase kernel name (e.g. ``"darwin"``, ``"linux"``).
        shell: Shell basename (e.g. ``"zsh"``, ``"bash"``).
        os_version: Kernel name and release (e.g. ``"Darwin 24.1.0"``).
        today_date: Timezone-aware datetime on the computer.
    """

    working_dir: str
    is_git_repo: bool
    platform: str
    shell: str
    os_version: str
    today_date: datetime


@dataclass(frozen=True)
class GitContext:
    """Git repository snapshot.

    Attributes:
        current_branch: Currently checked-out branch name.
        main_branch: Default/main branch name.
        status: Output of ``git status --short`` or similar.
        recent_commits: Formatted recent commit log.
    """

    current_branch: str
    main_branch: str
    status: str
    recent_commits: str


# ---------------------------------------------------------------------------
# MCP server configuration
# ---------------------------------------------------------------------------


class McpStdioServerConfig(TypedDict):
    """Configuration for a stdio-based MCP server.

    The subprocess is spawned with ``command`` and optional ``args`` / ``env``.
    """

    type: Literal["stdio"]
    command: str
    args: NotRequired[list[str]]
    env: NotRequired[dict[str, str]]


class McpSseServerConfig(TypedDict):
    """Configuration for an SSE-based MCP server."""

    type: Literal["sse"]
    url: str
    headers: NotRequired[dict[str, str]]


class McpHttpServerConfig(TypedDict):
    """Configuration for a Streamable-HTTP MCP server."""

    type: Literal["http"]
    url: str
    headers: NotRequired[dict[str, str]]


McpServerConfig = McpStdioServerConfig | McpSseServerConfig | McpHttpServerConfig
"""Union of all supported MCP server configurations.

Discriminated by the ``type`` key:

- ``"stdio"`` → :class:`McpStdioServerConfig`
- ``"sse"`` → :class:`McpSseServerConfig`
- ``"http"`` → :class:`McpHttpServerConfig`
"""


@dataclass(frozen=True)
class AgentContext:
    """Frozen snapshot of agent identity and capabilities.

    The single canonical context for prompt composition, reminder evaluation,
    and middleware state. Carries a ``ModelProfile`` (not just a name string)
    so consumers can access ``model.name`` and ``model.compaction_threshold``.

    Attributes:
        model: The model profile for this agent.
        tools: Currently registered tools.
        skills: Currently registered skills.
        mcps: Connected MCP clients.
        environment: Detected runtime environment, if available.
        git: Git repository snapshot, if available.
        agents: Registered subagent definitions.
    """

    model: ModelProfile
    tools: list[BaseAgentTool[Any]] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    mcps: list[McpClient] = field(default_factory=list)
    environment: EnvironmentContext | None = None
    git: GitContext | None = None
    agents: dict[str, AgentDefinition] = field(default_factory=dict)

    @property
    def model_name(self) -> str:
        """Model name string, delegated to ``model.name``."""
        return self.model.name

    @property
    def tool_name_vars(self) -> dict[str, str]:
        """Build ``${NAME_TOOL_NAME}`` template variables from registered tools.

        Returns a dict like ``{"BASH_TOOL_NAME": "Bash", "READ_TOOL_NAME": "Read", ...}``
        suitable for unpacking into :func:`~hexagent.prompts.content.substitute`.
        """
        return {f"{t.name.upper()}_TOOL_NAME": t.name for t in self.tools}
