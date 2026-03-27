"""Tests for langchain/middleware.py — the agent runtime engine.

Tests the pre-model pipeline (system prompt injection, compaction,
skill injection, reminder annotation) and tool call permission gating.
"""

# ruff: noqa: PLR2004, ANN401, ARG001
# mypy: disable-error-code="arg-type"

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from hexagent.harness.model import ModelProfile
from hexagent.harness.permission import PermissionDecision, PermissionGate, PermissionResult, SafetyRule
from hexagent.harness.reminders import Reminder
from hexagent.langchain.middleware import (
    _IMAGE_EXTRACTED,
    AgentMiddleware,
    HexAgentState,
    _create_denied_response,
    _detect_skill_call,
    _extract_text_content,
    _extract_tool_images,
)
from hexagent.prompts.content import load
from hexagent.types import AgentContext, CompactionPhase, Skill

if TYPE_CHECKING:
    from collections.abc import Sequence

from ..conftest import core_tools

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = "You are a test agent."


def _make_middleware(
    *,
    gate: PermissionGate | None = None,
    skill_resolver: Any = None,
    reminders: Sequence[Reminder] = (),
    approval_callback: Any = None,
    compaction_threshold: int = 100_000,
) -> AgentMiddleware:
    profile = ModelProfile(
        model=MagicMock(),
        compaction_threshold=compaction_threshold,
    )
    ctx = AgentContext(model=profile, tools=list(core_tools()))
    return AgentMiddleware(
        context=ctx,
        system_prompt=SYSTEM_PROMPT,
        permission_gate=gate or PermissionGate(),
        skill_resolver=skill_resolver,
        reminders=reminders,
        approval_callback=approval_callback,
    )


def _state(
    messages: list[SystemMessage | HumanMessage | AIMessage | ToolMessage],
    phase: CompactionPhase = CompactionPhase.NONE,
) -> HexAgentState:
    return {"messages": messages, "compaction_phase": phase}  # type: ignore[typeddict-item]


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------


class TestExtractTextContent:
    def test_string_content(self) -> None:
        assert _extract_text_content("hello") == "hello"

    def test_list_content(self) -> None:
        content = [{"type": "text", "text": "hello"}, " world"]
        assert _extract_text_content(content) == "hello world"


class TestCreateDeniedResponse:
    def test_denied_with_reason(self) -> None:
        request = type("R", (), {"tool_call": {"id": "call_1", "name": "bash", "args": {}}})()
        msg = _create_denied_response(request, "blocked")
        assert isinstance(msg, ToolMessage)
        assert "blocked" in msg.content

    def test_denied_without_reason(self) -> None:
        request = type("R", (), {"tool_call": {"id": "call_1", "name": "bash", "args": {}}})()
        msg = _create_denied_response(request, None)
        assert "Permission denied" in msg.content


class TestDetectSkillCall:
    """Tests for _detect_skill_call (operates on OpenAI-format messages)."""

    def _skill_tool_name(self) -> str:
        from hexagent.tools.skill import SkillTool

        return SkillTool.name

    def test_detects_recent_skill_call(self) -> None:
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "run commit"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": self._skill_tool_name(), "arguments": '{"skill": "commit"}'}},
                ],
            },
            {"role": "tool", "content": "Launching skill: commit", "tool_call_id": "tc_1"},
        ]
        assert _detect_skill_call(msgs) == "commit"

    def test_returns_none_if_no_skill_call(self) -> None:
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "echo hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": "bash", "arguments": '{"command": "echo hi"}'}},
                ],
            },
            {"role": "tool", "content": "hi", "tool_call_id": "tc_1"},
        ]
        assert _detect_skill_call(msgs) is None

    def test_returns_none_if_already_injected(self) -> None:
        """After skill injection, a user message follows the tool message."""
        msgs: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": self._skill_tool_name(), "arguments": '{"skill": "commit"}'}},
                ],
            },
            {"role": "tool", "content": "Launching skill: commit", "tool_call_id": "tc_1"},
            {"role": "user", "content": "<skill content>"},
        ]
        assert _detect_skill_call(msgs) is None

    def test_returns_none_for_empty_messages(self) -> None:
        assert _detect_skill_call([]) is None


# ---------------------------------------------------------------------------
# abefore_agent — system prompt injection
# ---------------------------------------------------------------------------


class TestSystemPromptInjection:
    async def test_injects_system_prompt_on_first_turn(self) -> None:
        mw = _make_middleware()
        state = _state([HumanMessage(content="Hello")])
        result = await mw.abefore_agent(state)
        assert result is not None
        messages = result["messages"].value
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == SYSTEM_PROMPT

    async def test_does_not_duplicate_system_prompt(self) -> None:
        mw = _make_middleware()
        state = _state([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content="Hello")])
        result = await mw.abefore_agent(state)
        # No overwrite needed — system prompt already present
        assert result is None


# ---------------------------------------------------------------------------
# abefore_model — compaction phases
# ---------------------------------------------------------------------------


class TestCompactionIntercept:
    async def test_requesting_phase_appends_compaction_prompt(self) -> None:
        mw = _make_middleware()
        state = _state(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content="Hello")],
            phase=CompactionPhase.REQUESTING,
        )
        result = await mw.abefore_model(state)
        assert result is not None
        messages = result["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == load("user_prompt_compaction_request")

    async def test_applying_phase_rebuilds_messages(self) -> None:
        mw = _make_middleware()
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
                AIMessage(content="This is the summary."),
            ],
            phase=CompactionPhase.APPLYING,
        )
        result = await mw.abefore_model(state)
        assert result is not None
        messages = result["messages"].value
        assert len(messages) == 2  # rebuilt: [SystemMessage, HumanMessage]
        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], HumanMessage)
        assert "This is the summary." in messages[1].content
        assert result["compaction_phase"] == CompactionPhase.NONE

    async def test_applying_phase_raises_if_last_message_not_ai(self) -> None:
        mw = _make_middleware()
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
            ],
            phase=CompactionPhase.APPLYING,
        )
        with pytest.raises(TypeError, match="AIMessage"):
            await mw.abefore_model(state)


# ---------------------------------------------------------------------------
# aafter_model — compaction trigger
# ---------------------------------------------------------------------------


def _ai_with_usage(content: str, total_tokens: int) -> AIMessage:
    """Create an AIMessage with usage_metadata for compaction tests."""
    return AIMessage(
        content=content,
        usage_metadata={"input_tokens": total_tokens - 100, "output_tokens": 100, "total_tokens": total_tokens},
    )


class TestCompactionTrigger:
    async def test_triggers_when_tokens_exceed_threshold(self) -> None:
        mw = _make_middleware(compaction_threshold=100_000)
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
                _ai_with_usage("Response", total_tokens=200_000),
            ]
        )
        result = await mw.aafter_model(state)
        assert result is not None
        assert result["compaction_phase"] == CompactionPhase.REQUESTING

    async def test_does_not_trigger_below_threshold(self) -> None:
        mw = _make_middleware(compaction_threshold=100_000)
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
                _ai_with_usage("Response", total_tokens=100),
            ]
        )
        result = await mw.aafter_model(state)
        assert result is None

    async def test_does_not_trigger_with_too_few_messages(self) -> None:
        mw = _make_middleware(compaction_threshold=100_000)
        state = _state([HumanMessage(content="short")])  # only 1 message
        result = await mw.aafter_model(state)
        assert result is None

    async def test_does_not_trigger_without_usage_metadata(self) -> None:
        mw = _make_middleware(compaction_threshold=100_000)
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
                AIMessage(content="Response"),  # no usage_metadata
            ]
        )
        result = await mw.aafter_model(state)
        assert result is None

    async def test_advances_from_requesting_to_applying(self) -> None:
        mw = _make_middleware()
        state = _state(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content="q"), AIMessage(content="summary")],
            phase=CompactionPhase.REQUESTING,
        )
        result = await mw.aafter_model(state)
        assert result is not None
        assert result["compaction_phase"] == CompactionPhase.APPLYING


# ---------------------------------------------------------------------------
# abefore_model — skill injection
# ---------------------------------------------------------------------------


class TestSkillInjection:
    _SKILL_NAME = "Skill"  # must match SkillTool.name

    async def test_injects_skill_content_after_skill_call(self) -> None:
        resolver = AsyncMock()
        resolver.load_content = AsyncMock(return_value="Skill content for commit")

        mw = _make_middleware(skill_resolver=resolver)
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="run commit"),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "tc_1", "name": self._SKILL_NAME, "args": {"skill": "commit"}}],
                ),
                ToolMessage(content="Launching skill: commit", tool_call_id="tc_1"),
            ]
        )
        result = await mw.abefore_model(state)
        assert result is not None
        appended = result["messages"]
        assert len(appended) == 1
        assert isinstance(appended[0], HumanMessage)
        assert "Skill content for commit" in appended[0].content

    async def test_no_injection_without_skill_call(self) -> None:
        resolver = AsyncMock()
        mw = _make_middleware(skill_resolver=resolver)
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
            ]
        )
        result = await mw.abefore_model(state)
        # No overwrite because system prompt already exists
        assert result is None
        resolver.load_content.assert_not_called()

    async def test_skill_load_failure_injects_reminder(self) -> None:
        resolver = AsyncMock()
        resolver.load_content = AsyncMock(side_effect=KeyError("not found"))

        mw = _make_middleware(skill_resolver=resolver)
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="run unknown"),
                AIMessage(
                    content="",
                    tool_calls=[{"id": "tc_1", "name": self._SKILL_NAME, "args": {"skill": "unknown"}}],
                ),
                ToolMessage(content="Launching skill: unknown", tool_call_id="tc_1"),
            ]
        )
        result = await mw.abefore_model(state)
        assert result is not None
        appended = result["messages"]
        assert len(appended) == 1
        assert isinstance(appended[0], HumanMessage)
        assert "<system-reminder>" in appended[0].content
        assert "unknown" in appended[0].content


# ---------------------------------------------------------------------------
# abefore_model — reminder annotation
# ---------------------------------------------------------------------------


class TestReminderAnnotation:
    def _skill_reminder(self) -> Reminder:
        """A reminder that fires when skills are present."""

        def rule(messages: Any, ctx: AgentContext) -> str | None:
            if ctx.skills:
                return "Skills available!"
            return None

        return Reminder(rule=rule, position="prepend")

    async def test_prepends_reminder_to_last_message(self) -> None:
        profile = ModelProfile(model=MagicMock(), compaction_threshold=100_000)
        ctx = AgentContext(
            model=profile,
            tools=list(core_tools()),
            skills=[Skill(name="commit", description="desc", path="/p")],
        )
        mw = AgentMiddleware(
            context=ctx,
            system_prompt=SYSTEM_PROMPT,
            permission_gate=PermissionGate(),
            reminders=[self._skill_reminder()],
        )

        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
            ]
        )
        result = await mw.abefore_model(state)
        assert result is not None
        messages = result["messages"].value
        last_content = messages[-1].content
        assert "<system-reminder>" in last_content
        assert "Skills available!" in last_content

    async def test_no_annotation_without_matching_reminders(self) -> None:
        mw = _make_middleware(
            reminders=[self._skill_reminder()],
        )
        # No skills → reminder returns None

        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="Hello"),
            ]
        )
        result = await mw.abefore_model(state)
        assert result is None


# ---------------------------------------------------------------------------
# awrap_tool_call — permission gating
# ---------------------------------------------------------------------------


class _DenyBashRule(SafetyRule):
    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision | None:
        if tool_name == "bash":
            return PermissionDecision(result=PermissionResult.DENIED, reason="bash blocked")
        return None


class _ApprovalRule(SafetyRule):
    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision | None:
        return PermissionDecision(
            result=PermissionResult.NEEDS_APPROVAL,
            approval_prompt="Approve this?",
        )


class TestPermissionGating:
    async def test_allowed_call_passes_through(self) -> None:
        mw = _make_middleware()
        handler = AsyncMock(return_value=ToolMessage(content="ok", tool_call_id="tc_1"))
        request = type("R", (), {"tool_call": {"id": "tc_1", "name": "bash", "args": {}}})()
        result = await mw.awrap_tool_call(request, handler)
        handler.assert_awaited_once()
        assert isinstance(result, ToolMessage)
        assert result.content == "ok"

    async def test_denied_call_returns_error(self) -> None:
        gate = PermissionGate()
        gate.register_rule(_DenyBashRule())
        mw = _make_middleware(gate=gate)
        handler = AsyncMock()
        request = type("R", (), {"tool_call": {"id": "tc_1", "name": "bash", "args": {}}})()
        result = await mw.awrap_tool_call(request, handler)
        handler.assert_not_awaited()
        assert isinstance(result, ToolMessage)
        assert "bash blocked" in result.content

    async def test_needs_approval_denied_without_callback(self) -> None:
        gate = PermissionGate()
        gate.register_rule(_ApprovalRule())
        mw = _make_middleware(gate=gate, approval_callback=None)
        handler = AsyncMock()
        request = type("R", (), {"tool_call": {"id": "tc_1", "name": "read", "args": {}}})()
        result = await mw.awrap_tool_call(request, handler)
        handler.assert_not_awaited()
        assert isinstance(result, ToolMessage)
        assert "requires approval" in result.content

    async def test_needs_approval_approved_by_callback(self) -> None:
        gate = PermissionGate()
        gate.register_rule(_ApprovalRule())
        callback = AsyncMock(return_value=True)
        mw = _make_middleware(gate=gate, approval_callback=callback)
        handler = AsyncMock(return_value=ToolMessage(content="ok", tool_call_id="tc_1"))
        request = type("R", (), {"tool_call": {"id": "tc_1", "name": "read", "args": {}}})()
        result = await mw.awrap_tool_call(request, handler)
        callback.assert_awaited_once()
        handler.assert_awaited_once()
        assert isinstance(result, ToolMessage)
        assert result.content == "ok"

    async def test_needs_approval_rejected_by_callback(self) -> None:
        gate = PermissionGate()
        gate.register_rule(_ApprovalRule())
        callback = AsyncMock(return_value=False)
        mw = _make_middleware(gate=gate, approval_callback=callback)
        handler = AsyncMock()
        request = type("R", (), {"tool_call": {"id": "tc_1", "name": "read", "args": {}}})()
        result = await mw.awrap_tool_call(request, handler)
        handler.assert_not_awaited()
        assert isinstance(result, ToolMessage)
        assert "denied by user" in result.content


# ---------------------------------------------------------------------------
# Tools property
# ---------------------------------------------------------------------------


class TestToolsProperty:
    def test_returns_langchain_tools(self) -> None:
        mw = _make_middleware()
        tools = mw.tools
        assert len(tools) == 6

    def test_tools_are_cached(self) -> None:
        mw = _make_middleware()
        first = mw.tools
        second = mw.tools
        assert first is second


# ---------------------------------------------------------------------------
# Image extraction — _extract_tool_images helper
# ---------------------------------------------------------------------------


class TestExtractToolImages:
    """Tests for _extract_tool_images (pure function)."""

    def test_extracts_images_from_tool_message(self) -> None:
        messages: list[HumanMessage | AIMessage | ToolMessage] = [
            HumanMessage(content="read img.png"),
            AIMessage(content="", tool_calls=[{"id": "tc_1", "name": "read", "args": {}}]),
            ToolMessage(
                content=[
                    {"type": "text", "text": "[Image: img.png]"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
                tool_call_id="tc_1",
            ),
        ]
        result = _extract_tool_images(messages)
        assert result is not None
        assert len(result) == 4  # original 3 + injected HumanMessage

        # ToolMessage should have text only
        tool_msg = result[2]
        assert isinstance(tool_msg, ToolMessage)
        assert isinstance(tool_msg.content, list)
        assert all(b.get("type") != "image_url" for b in tool_msg.content if isinstance(b, dict))
        assert tool_msg.additional_kwargs[_IMAGE_EXTRACTED] is True

        # Injected HumanMessage should have the image
        human_msg = result[3]
        assert isinstance(human_msg, HumanMessage)
        assert isinstance(human_msg.content, list)
        image_blocks = [b for b in human_msg.content if isinstance(b, dict) and b.get("type") == "image_url"]
        assert len(image_blocks) == 1

    def test_handles_anthropic_image_format(self) -> None:
        messages: list[ToolMessage] = [
            ToolMessage(
                content=[
                    {"type": "text", "text": "screenshot"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}},
                ],
                tool_call_id="tc_1",
            ),
        ]
        result = _extract_tool_images(messages)
        assert result is not None
        assert len(result) == 2
        human_msg = result[1]
        assert isinstance(human_msg, HumanMessage)
        image_blocks = [b for b in human_msg.content if isinstance(b, dict) and b.get("type") == "image"]
        assert len(image_blocks) == 1

    def test_no_extraction_when_no_images(self) -> None:
        messages: list[ToolMessage] = [
            ToolMessage(
                content=[{"type": "text", "text": "just text"}],
                tool_call_id="tc_1",
            ),
        ]
        assert _extract_tool_images(messages) is None

    def test_no_extraction_for_string_content(self) -> None:
        messages: list[ToolMessage] = [
            ToolMessage(content="plain string", tool_call_id="tc_1"),
        ]
        assert _extract_tool_images(messages) is None

    def test_idempotent_skips_already_extracted(self) -> None:
        messages: list[ToolMessage | HumanMessage] = [
            ToolMessage(
                content=[{"type": "text", "text": "[see image below]"}],
                tool_call_id="tc_1",
                additional_kwargs={_IMAGE_EXTRACTED: True},
            ),
            HumanMessage(
                content=[
                    {"type": "text", "text": "[Image from tool result]"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ]
            ),
        ]
        assert _extract_tool_images(messages) is None

    def test_uses_placeholder_when_only_images(self) -> None:
        """When ToolMessage has no text blocks, use a string placeholder."""
        messages: list[ToolMessage] = [
            ToolMessage(
                content=[
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                ],
                tool_call_id="tc_1",
            ),
        ]
        result = _extract_tool_images(messages)
        assert result is not None
        tool_msg = result[0]
        assert isinstance(tool_msg, ToolMessage)
        assert tool_msg.content == "[see image below]"

    def test_preserves_tool_call_id(self) -> None:
        messages: list[ToolMessage] = [
            ToolMessage(
                content=[
                    {"type": "text", "text": "img"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}},
                ],
                tool_call_id="tc_42",
                id="msg_7",
            ),
        ]
        result = _extract_tool_images(messages)
        assert result is not None
        tool_msg = result[0]
        assert isinstance(tool_msg, ToolMessage)
        assert tool_msg.tool_call_id == "tc_42"
        assert tool_msg.id == "msg_7"


# ---------------------------------------------------------------------------
# abefore_model — image extraction integration
# ---------------------------------------------------------------------------


class TestImageExtractionPipeline:
    """Tests for image extraction in the abefore_model pipeline."""

    async def test_extracts_images_for_non_anthropic_model(self) -> None:
        """Non-Anthropic model (MagicMock) triggers image extraction."""
        mw = _make_middleware()
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="read img.png"),
                AIMessage(content="", tool_calls=[{"id": "tc_1", "name": "read", "args": {}}]),
                ToolMessage(
                    content=[
                        {"type": "text", "text": "[Image: img.png]"},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
                    ],
                    tool_call_id="tc_1",
                ),
            ]
        )
        result = await mw.abefore_model(state)
        assert result is not None
        messages = result["messages"].value
        # Should have 5 messages: sys + human + ai + tool (text only) + human (image)
        assert len(messages) == 5
        assert isinstance(messages[4], HumanMessage)
        image_blocks = [b for b in messages[4].content if isinstance(b, dict) and b.get("type") == "image_url"]
        assert len(image_blocks) == 1

    async def test_no_extraction_when_no_images(self) -> None:
        mw = _make_middleware()
        state = _state(
            [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content="hello"),
            ]
        )
        result = await mw.abefore_model(state)
        assert result is None
