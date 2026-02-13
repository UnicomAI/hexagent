"""System reminder rules for dynamic message annotation.

Reminder rules evaluate conversation state and return content to inject
as ``<system-reminder>`` tags. Rules receive messages as OpenAI-compatible
dicts (framework-agnostic) and a context snapshot of agent capabilities.

Each rule is a callable: ``(messages, ctx) -> str | None``.
Returning ``None`` opts out. Returning a string triggers injection.
Position (prepend/append to last message) is metadata at registration time.

Built-in rules are defined at the bottom of this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from openagent.prompts.content import load, substitute
from openagent.prompts.tags import SYSTEM_REMINDER_TAG, Tag

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from openagent.types import AgentContext

# OpenAI-compatible message format.
# Expected keys: "role" (str), "content" (str | list),
# optional "tool_calls", "tool_call_id".
Message = dict[str, Any]


@dataclass(frozen=True)
class Reminder:
    """A reminder rule with injection position metadata.

    Attributes:
        rule: Callable that evaluates messages and returns content or None.
        position: Where to inject the reminder into the last message.
    """

    rule: Callable[[Sequence[Message], AgentContext], str | None]
    position: Literal["prepend", "append"] = "prepend"


def evaluate_reminders(
    reminders: Sequence[Reminder],
    messages: Sequence[Message],
    ctx: AgentContext,
    tag: Tag = SYSTEM_REMINDER_TAG,
) -> tuple[list[str], list[str]]:
    """Evaluate reminder rules and return tagged strings ready for injection.

    All rules evaluate against the ORIGINAL message list (not each other's
    output). Each non-None result is wrapped in ``<tag>`` and sorted by
    position.

    Args:
        reminders: Rules to evaluate (in declared order).
        messages: Message history as OpenAI-compatible dicts.
        ctx: Snapshot of agent capabilities.
        tag: Callable tag to wrap each reminder.

    Returns:
        (prepends, appends) — tagged strings ready for injection.
    """
    prepends: list[str] = []
    appends: list[str] = []
    for reminder in reminders:
        content = reminder.rule(messages, ctx)
        if content is not None:
            wrapped = tag(content)
            if reminder.position == "prepend":
                prepends.append(wrapped)
            else:
                appends.append(wrapped)
    return prepends, appends


# ---------------------------------------------------------------------------
# Built-in reminder rules
# ---------------------------------------------------------------------------


def initial_available_skills(
    messages: Sequence[Message],
    ctx: AgentContext,
) -> str | None:
    """Inject available skills list into the first user message.

    Fires only at the very beginning of a conversation session
    (single user message, no prior model responses) when skills
    are available.
    """
    if len(messages) != 1 or messages[0].get("role") != "user":
        return None

    if not ctx.skills:
        return None

    template = load("system_reminder_initial_available_skills")
    formatted = "\n".join(f"- {s.name}: {s.description}" for s in ctx.skills)
    return substitute(template, **ctx.tool_name_vars, FORMATTED_SKILLS_LIST=formatted)


BUILTIN_REMINDERS: Sequence[Reminder] = [
    Reminder(rule=initial_available_skills, position="prepend"),
]
"""Default reminder rules for all sessions."""
