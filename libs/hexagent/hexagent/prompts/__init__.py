"""Prompt infrastructure for building agent system prompts.

Three layers:
- Content: ``load``/``find`` for read-only .md fragment text
- Sections: self-contained functions producing prompt sections
- Compose: ``compose()`` joins sections via profiles
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from hexagent.prompts import sections
from hexagent.prompts.content import find, load, substitute
from hexagent.types import AgentContext, GitContext

SectionFn = Callable[[AgentContext], str | None]
"""A section function: takes context, returns content or None to opt out."""


def compose(profile: Sequence[SectionFn], ctx: AgentContext) -> str:
    """Compose a system prompt from a profile and context.

    Args:
        profile: Ordered list of section functions.
        ctx: Runtime state snapshot.

    Returns:
        The assembled prompt string.
    """
    return "\n\n".join(section_text for fn in profile if (section_text := fn(ctx)) is not None)


FRESH_SESSION: Sequence[SectionFn] = [
    sections.identity,
    sections.agency,
    sections.doing_tasks,
    sections.executing_actions_with_care,
    sections.tone_and_style,
    sections.computer_use,
    sections.using_your_tools,
    sections.tool_instructions,
    sections.mcps,
]
"""Profile for a new conversation session."""

RESUMED_SESSION: Sequence[SectionFn] = [
    sections.identity,
    sections.agency,
    sections.doing_tasks,
    sections.executing_actions_with_care,
    sections.tone_and_style,
    sections.computer_use,
    sections.using_your_tools,
    sections.tool_instructions,
    sections.mcps,
]
"""Profile for a session resumed from compaction. Same as FRESH for now."""

SUBAGENT_SESSION: Sequence[SectionFn] = [
    sections.computer_use,
    sections.tool_instructions,
    sections.mcps,
]
"""Profile for subagent sessions.

Stripped-down: no identity, agency, doing_tasks, executing_actions_with_care,
tone_and_style. The developer's definition.system_prompt is prepended by
the spawn function.
"""

__all__ = [
    "FRESH_SESSION",
    "RESUMED_SESSION",
    "SUBAGENT_SESSION",
    "AgentContext",
    "GitContext",
    "SectionFn",
    "compose",
    "find",
    "load",
    "sections",
    "substitute",
]
