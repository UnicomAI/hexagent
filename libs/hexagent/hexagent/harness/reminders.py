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

from hexagent.prompts.content import load, substitute
from hexagent.prompts.tags import SYSTEM_REMINDER_TAG, Tag

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hexagent.tasks import TaskRegistry
    from hexagent.types import AgentContext

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


def available_skills_reminder(
    messages: Sequence[Message],
    ctx: AgentContext,
) -> str | None:
    """Inject available skills list into the first user message.

    Fires only at the very beginning of a conversation session
    (single user message, no prior model responses) when skills
    are available.
    """
    _max_initial_messages = 2  # At most: [system?, user]
    if not messages or len(messages) > _max_initial_messages or messages[-1].get("role") != "user":
        return None

    if not ctx.skills:
        return None

    template = load("system_reminder_initial_available_skills")
    formatted = "\n".join(f"- {s.name}: {s.description}" for s in ctx.skills)
    return substitute(template, **ctx.tool_name_vars, FORMATTED_SKILLS_LIST=formatted)


def task_completion_reminder(registry: TaskRegistry) -> Reminder:
    """Create a reminder that surfaces background task completions.

    Drains completed/failed tasks from the registry and formats them
    as ``<task-notification>`` blocks for the agent.

    Args:
        registry: The task registry to drain completions from.
    """

    def _rule(_messages: Sequence[Message], _ctx: AgentContext) -> str | None:
        completions = registry.drain_completions()
        if not completions:
            return None
        status_headers: dict[str, str] = {
            "completed": "A background task completed",
            "failed": "A background task failed",
        }
        parts = [
            f"{status_headers.get(c.status, f'Background task {c.status}')}:\n"
            f"<task-notification>\n"
            f"<task-id>{c.task_id}</task-id>\n"
            f"<kind>{c.kind}</kind>\n"
            f"<status>{c.status}</status>\n"
            f'<summary>Task "{c.description}" {c.status}</summary>\n'
            f"<result>{c.result.to_text()}</result>\n"
            f"</task-notification>"
            for c in completions
        ]
        return "\n\n".join(parts)

    return Reminder(rule=_rule, position="append")


BUILTIN_REMINDERS: Sequence[Reminder] = [
    Reminder(rule=available_skills_reminder, position="prepend"),
]
"""Default reminder rules for all sessions.

Note: :func:`task_completion_reminder` is also a built-in reminder but requires
a :class:`~hexagent.tasks.TaskRegistry` instance. It is added
unconditionally by the agent factory.
"""
