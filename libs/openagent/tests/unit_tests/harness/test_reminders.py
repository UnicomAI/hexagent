"""Tests for harness/reminders.py — evaluate_reminders, built-in rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from openagent.harness.reminders import (
    BUILTIN_REMINDERS,
    Message,
    Reminder,
    evaluate_reminders,
    initial_available_skills,
)
from openagent.prompts.tags import SYSTEM_REMINDER_TAG, Tag
from openagent.types import AgentContext, Skill

if TYPE_CHECKING:
    from collections.abc import Sequence

from ..conftest import make_tool

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user_msg(text: str) -> Message:
    return {"role": "user", "content": text}


def _assistant_msg(text: str) -> Message:
    return {"role": "assistant", "content": text}


def _always_fire(_messages: Sequence[Message], _ctx: AgentContext) -> str | None:
    return "reminder content"


def _never_fire(_messages: Sequence[Message], _ctx: AgentContext) -> str | None:
    return None


# ---------------------------------------------------------------------------
# evaluate_reminders
# ---------------------------------------------------------------------------


class TestEvaluateReminders:
    def test_no_reminders_returns_empty(self) -> None:
        prepends, appends = evaluate_reminders([], [_user_msg("hi")], AgentContext())
        assert prepends == []
        assert appends == []

    def test_prepend_reminder_wraps_in_tag(self) -> None:
        r = Reminder(rule=_always_fire, position="prepend")
        prepends, appends = evaluate_reminders([r], [_user_msg("hi")], AgentContext())
        assert len(prepends) == 1
        assert prepends[0] == SYSTEM_REMINDER_TAG("reminder content")
        assert appends == []

    def test_append_reminder_wraps_in_tag(self) -> None:
        r = Reminder(rule=_always_fire, position="append")
        prepends, appends = evaluate_reminders([r], [_user_msg("hi")], AgentContext())
        assert prepends == []
        assert len(appends) == 1
        assert appends[0] == SYSTEM_REMINDER_TAG("reminder content")

    def test_none_rules_are_filtered(self) -> None:
        reminders = [
            Reminder(rule=_never_fire, position="prepend"),
            Reminder(rule=_always_fire, position="append"),
        ]
        prepends, appends = evaluate_reminders(reminders, [_user_msg("hi")], AgentContext())
        assert prepends == []
        assert len(appends) == 1

    def test_multiple_reminders_sorted_by_position(self) -> None:
        reminders = [
            Reminder(rule=_always_fire, position="prepend"),
            Reminder(rule=_always_fire, position="append"),
        ]
        prepends, appends = evaluate_reminders(reminders, [_user_msg("hi")], AgentContext())
        assert len(prepends) == 1
        assert len(appends) == 1

    def test_custom_tag_name(self) -> None:
        r = Reminder(rule=_always_fire, position="prepend")
        custom = Tag("custom")
        prepends, _ = evaluate_reminders([r], [_user_msg("hi")], AgentContext(), tag=custom)
        assert prepends[0] == custom("reminder content")


# ---------------------------------------------------------------------------
# initial_available_skills (built-in rule)
# ---------------------------------------------------------------------------


class TestInitialAvailableSkills:
    def _ctx_with_skills(self) -> AgentContext:
        return AgentContext(
            tools=[make_tool("Skill")],
            skills=[Skill(name="commit", description="Git commits", path="/s/commit")],
        )

    def test_fires_on_first_user_message(self) -> None:
        messages: list[Message] = [_user_msg("Hello")]
        result = initial_available_skills(messages, self._ctx_with_skills())
        assert result is not None
        assert "commit" in result

    def test_returns_none_after_assistant_response(self) -> None:
        messages: list[Message] = [_user_msg("Hello"), _assistant_msg("Hi")]
        result = initial_available_skills(messages, self._ctx_with_skills())
        assert result is None

    def test_returns_none_without_skills(self) -> None:
        messages: list[Message] = [_user_msg("Hello")]
        result = initial_available_skills(messages, AgentContext())
        assert result is None

    def test_returns_none_for_empty_messages(self) -> None:
        result = initial_available_skills([], AgentContext())
        assert result is None

    def test_returns_none_for_non_user_first_message(self) -> None:
        messages: list[Message] = [_assistant_msg("System init")]
        result = initial_available_skills(messages, self._ctx_with_skills())
        assert result is None

    def test_includes_all_skill_names(self) -> None:
        ctx = AgentContext(
            tools=[make_tool("Skill")],
            skills=[
                Skill(name="commit", description="Git commits", path="/s/commit"),
                Skill(name="review", description="Code review", path="/s/review"),
            ],
        )
        result = initial_available_skills([_user_msg("Hello")], ctx)
        assert result is not None
        assert "commit" in result
        assert "review" in result


class TestBuiltinReminders:
    def test_contains_initial_available_skills(self) -> None:
        assert len(BUILTIN_REMINDERS) >= 1
        assert BUILTIN_REMINDERS[0].rule is initial_available_skills
        assert BUILTIN_REMINDERS[0].position == "prepend"
