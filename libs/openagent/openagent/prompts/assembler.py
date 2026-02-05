"""System prompt assembler with recipe-driven composition.

The assembler iterates an explicit RECIPE of fragment references,
evaluates conditions, renders included fragments via the
``PromptLibrary``, and joins them with double newlines.

Design follows Claude Code's pattern: the RECIPE is explicit data,
not buried in code logic.  To reorder or conditionally include
sections, modify the RECIPE list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable

    from openagent.prompts.library import PromptLibrary
    from openagent.tools.base import BaseAgentTool
    from openagent.types import MCPServer, Skill


# ---------------------------------------------------------------------------
# Context and fragment reference types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssemblerContext:
    """Data available for condition evaluation during assembly.

    Attributes:
        tools: Registered tools.
        skills: Registered skills.
        mcps: Registered MCP servers.
        environment: Environment key-value pairs.
        user_instructions: Optional user instructions text.
    """

    tools: list[BaseAgentTool[Any]] = field(default_factory=list)
    skills: list[Skill] = field(default_factory=list)
    mcps: list[MCPServer] = field(default_factory=list)
    environment: dict[str, str] = field(default_factory=dict)
    user_instructions: str | None = None


@dataclass(frozen=True)
class FragmentRef:
    """A reference to a prompt fragment with an optional condition.

    Attributes:
        key: The template key in the PromptLibrary.
        condition: A callable that receives an ``AssemblerContext``
            and returns ``True`` if the fragment should be included.
            ``None`` means always include.
    """

    key: str
    condition: Callable[[AssemblerContext], bool] | None = None


# ---------------------------------------------------------------------------
# Condition functions
# ---------------------------------------------------------------------------


def _has_tools(ctx: AssemblerContext) -> bool:
    return len(ctx.tools) > 0


def _has_skills(ctx: AssemblerContext) -> bool:
    return len(ctx.skills) > 0


def _has_mcps(ctx: AssemblerContext) -> bool:
    return len(ctx.mcps) > 0


def _has_environment(ctx: AssemblerContext) -> bool:
    return len(ctx.environment) > 0


def _has_user_instructions(ctx: AssemblerContext) -> bool:
    return ctx.user_instructions is not None and len(ctx.user_instructions) > 0


# ---------------------------------------------------------------------------
# Dynamic variable builders
# ---------------------------------------------------------------------------


def _build_dynamic_vars(
    ctx: AssemblerContext,
    library: PromptLibrary,
) -> dict[str, str]:
    """Build dynamic template variables from the assembler context.

    Tool instructions are concatenated directly from ``tools/*.md``
    fragment files in the library.  Skills, MCPs, and environment
    are formatted as simple lists.

    Args:
        ctx: The assembler context.
        library: The prompt library for looking up tool instructions.

    Returns:
        Dictionary of dynamic variable names to rendered values.
    """
    dynamic: dict[str, str] = {}

    if ctx.tools:
        sections: list[str] = []
        for tool in ctx.tools:
            key = f"tools/{tool.name}"
            if library.has(key):
                sections.append(f"## {tool.name}\n\n{library.get(key)}")
        dynamic["tool_instructions"] = "\n\n---\n\n".join(sections)

    # Auto-derive tool name variables for cross-references in .md files.
    # E.g., tool named "bash" creates variable {tool_bash} with value "bash".
    for tool in ctx.tools:
        dynamic[f"tool_{tool.name}"] = tool.name

    if ctx.skills:
        dynamic["skill_list"] = "\n".join(f"- **{s.name}**: {s.description}" for s in ctx.skills)

    if ctx.mcps:
        dynamic["mcp_list"] = "\n".join(f"- **{m.name}**: {m.description}" for m in ctx.mcps)

    if ctx.environment:
        dynamic["environment_list"] = "\n".join(f"- {k}: {v}" for k, v in ctx.environment.items())

    if ctx.user_instructions:
        dynamic["user_instructions"] = ctx.user_instructions

    return dynamic


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------


class SystemPromptAssembler:
    """Assembles system prompt from fragment templates using a RECIPE.

    The RECIPE is an ordered list of ``FragmentRef`` entries. Each entry
    points to a template key in the ``PromptLibrary`` and optionally
    specifies a condition.  Subclasses can override RECIPE to change
    ordering or add custom fragments.

    Examples:
        ```python
        assembler = SystemPromptAssembler()
        prompt = assembler.assemble(
            library=library,
            tools=registry.get_tools(),
            environment={{"platform": "darwin"}},
        )
        ```

        Custom ordering via subclass::

            class CustomAssembler(SystemPromptAssembler):
                RECIPE = [
                    FragmentRef("system/base"),
                    FragmentRef("system/environment", condition=_has_environment),
                    FragmentRef("system/tools", condition=_has_tools),
                ]
    """

    RECIPE: ClassVar[list[FragmentRef]] = [
        FragmentRef("system/base"),
        FragmentRef("system/tools", condition=_has_tools),
        FragmentRef("system/skills", condition=_has_skills),
        FragmentRef("system/mcps", condition=_has_mcps),
        FragmentRef("system/environment", condition=_has_environment),
        FragmentRef("system/user_instructions", condition=_has_user_instructions),
    ]

    def assemble(
        self,
        *,
        library: PromptLibrary,
        tools: list[BaseAgentTool[Any]] | None = None,
        skills: list[Skill] | None = None,
        mcps: list[MCPServer] | None = None,
        environment: dict[str, str] | None = None,
        user_instructions: str | None = None,
    ) -> str:
        """Assemble the system prompt from fragments.

        Args:
            library: The prompt template library.
            tools: List of tools to include.
            skills: List of skills to include.
            mcps: List of MCP servers to include.
            environment: Environment context as key-value pairs.
            user_instructions: Additional user instructions.

        Returns:
            The assembled system prompt string.
        """
        ctx = AssemblerContext(
            tools=tools or [],
            skills=skills or [],
            mcps=mcps or [],
            environment=environment or {},
            user_instructions=user_instructions,
        )

        merged = _build_dynamic_vars(ctx, library)

        sections: list[str] = []
        for ref in self.RECIPE:
            if ref.condition is not None and not ref.condition(ctx):
                continue
            rendered = library.render(ref.key, merged)
            sections.append(rendered)

        return "\n\n".join(sections)
