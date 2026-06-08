"""Unit tests for middleware helper functions.

Focuses on ``_supports_tool_images``, ``_extract_tool_images``,
``_detect_skill_call``, and ``AgentMiddleware.awrap_tool_call`` —
the permission-gating entry point.

These tests are intentionally lightweight and target public-accessible
helpers that have no coverage elsewhere.
"""

# ruff: noqa: PLR2004, ANN401
# mypy: disable-error-code="arg-type"

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from uniharness.harness.permission import PermissionDecision, PermissionGate, PermissionResult, SafetyRule
from uniharness.langchain.middleware import (
    _IMAGE_EXTRACTED,
    AgentMiddleware,
    _detect_skill_call,
    _extract_tool_images,
    _supports_tool_images,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gate_with_rule(rule: SafetyRule) -> PermissionGate:
    gate = PermissionGate()
    gate.register_rule(rule)
    return gate


def _make_request(tool_name: str = "bash", tool_id: str = "tc_1") -> Any:
    return type("R", (), {"tool_call": {"id": tool_id, "name": tool_name, "args": {}}})()


def _make_middleware(
    gate: PermissionGate | None = None,
    approval_callback: Any = None,
) -> AgentMiddleware:
    from tests.unit_tests.conftest import core_tools
    from uniharness.harness.model import ModelProfile
    from uniharness.types import AgentContext

    profile = ModelProfile(model=MagicMock(), compaction_threshold=100_000)
    ctx = AgentContext(model=profile, tools=list(core_tools()))
    return AgentMiddleware(
        context=ctx,
        system_prompt="You are a test agent.",
        permission_gate=gate or PermissionGate(),
        approval_callback=approval_callback,
    )


# ---------------------------------------------------------------------------
# _supports_tool_images
# ---------------------------------------------------------------------------


class TestSupportsToolImages:
    """``_supports_tool_images`` returns True only for ChatAnthropic instances."""

    def test_returns_false_for_magic_mock(self) -> None:
        """MagicMock is not a ChatAnthropic instance."""
        assert _supports_tool_images(MagicMock()) is False

    def test_returns_false_when_langchain_anthropic_not_installed(self) -> None:
        """If import fails the function must return False without raising."""
        import importlib
        import sys

        import uniharness.langchain.middleware as mod

        # Temporarily hide langchain_anthropic so the module re-runs its try/except
        original = sys.modules.get("langchain_anthropic")
        sys.modules["langchain_anthropic"] = None  # type: ignore[assignment]
        try:
            importlib.reload(mod)
            result = mod._supports_tool_images(MagicMock())
        finally:
            if original is None:
                sys.modules.pop("langchain_anthropic", None)
            else:
                sys.modules["langchain_anthropic"] = original
            importlib.reload(mod)
        assert result is False

    def test_returns_true_for_chat_anthropic_instance(self) -> None:
        """ChatAnthropic instance yields True (requires langchain_anthropic)."""
        pytest.importorskip("langchain_anthropic")
        from langchain_anthropic import ChatAnthropic

        # ChatAnthropic requires an API key; patch __init__ to avoid it.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ChatAnthropic, "__init__", lambda *_: None)
            model = ChatAnthropic.__new__(ChatAnthropic)
        assert _supports_tool_images(model) is True


# ---------------------------------------------------------------------------
# _extract_tool_images
# ---------------------------------------------------------------------------


class TestExtractToolImages:
    """Pure-function tests for image extraction from ToolMessages."""

    def test_returns_none_when_no_messages(self) -> None:
        assert _extract_tool_images([]) is None

    def test_returns_none_for_string_content_tool_message(self) -> None:
        msgs: list[ToolMessage] = [ToolMessage(content="plain text", tool_call_id="tc_1")]
        assert _extract_tool_images(msgs) is None

    def test_returns_none_when_no_image_blocks(self) -> None:
        msgs: list[ToolMessage] = [
            ToolMessage(
                content=[{"type": "text", "text": "just text"}],
                tool_call_id="tc_1",
            )
        ]
        assert _extract_tool_images(msgs) is None

    def test_extracts_image_url_block_into_human_message(self) -> None:
        msgs: list[HumanMessage | AIMessage | ToolMessage] = [
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
        result = _extract_tool_images(msgs)
        assert result is not None
        # Original 3 messages + 1 injected HumanMessage
        assert len(result) == 4
        human_msg = result[3]
        assert isinstance(human_msg, HumanMessage)
        assert isinstance(human_msg.content, list)
        image_blocks = [b for b in human_msg.content if isinstance(b, dict) and b.get("type") == "image_url"]
        assert len(image_blocks) == 1

    def test_extracted_tool_message_marked_and_text_preserved(self) -> None:
        msgs: list[ToolMessage] = [
            ToolMessage(
                content=[
                    {"type": "text", "text": "caption"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}},
                ],
                tool_call_id="tc_1",
            )
        ]
        result = _extract_tool_images(msgs)
        assert result is not None
        tool_msg = result[0]
        assert isinstance(tool_msg, ToolMessage)
        assert tool_msg.additional_kwargs.get(_IMAGE_EXTRACTED) is True
        # Text blocks must survive
        assert any(isinstance(b, dict) and b.get("text") == "caption" for b in (tool_msg.content if isinstance(tool_msg.content, list) else []))

    def test_placeholder_when_tool_message_has_only_images(self) -> None:
        """When all content is images, use '[see image below]' as placeholder."""
        msgs: list[ToolMessage] = [
            ToolMessage(
                content=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}],
                tool_call_id="tc_1",
            )
        ]
        result = _extract_tool_images(msgs)
        assert result is not None
        tool_msg = result[0]
        assert isinstance(tool_msg, ToolMessage)
        assert tool_msg.content == "[see image below]"

    def test_idempotent_skips_already_extracted(self) -> None:
        """Messages already marked with _IMAGE_EXTRACTED are not processed again."""
        msgs: list[ToolMessage | HumanMessage] = [
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
        # Must return None — nothing changed
        assert _extract_tool_images(msgs) is None

    def test_preserves_tool_call_id_and_message_id(self) -> None:
        msgs: list[ToolMessage] = [
            ToolMessage(
                content=[
                    {"type": "text", "text": "data"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "x"}},
                ],
                tool_call_id="tc_99",
                id="msg_42",
            )
        ]
        result = _extract_tool_images(msgs)
        assert result is not None
        tool_msg = result[0]
        assert isinstance(tool_msg, ToolMessage)
        assert tool_msg.tool_call_id == "tc_99"
        assert tool_msg.id == "msg_42"


# ---------------------------------------------------------------------------
# _detect_skill_call
# ---------------------------------------------------------------------------


class TestDetectSkillCall:
    """``_detect_skill_call`` operates on OpenAI-format messages."""

    def _skill_name(self) -> str:
        from uniharness.tools.skill import SkillTool

        return SkillTool.name

    def test_returns_none_for_empty_list(self) -> None:
        assert _detect_skill_call([]) is None

    def test_detects_skill_from_last_tool_message(self) -> None:
        msgs: list[dict[str, Any]] = [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": self._skill_name(), "arguments": '{"skill": "deploy"}'}},
                ],
            },
            {"role": "tool", "content": "Launching skill: deploy", "tool_call_id": "tc_1"},
        ]
        assert _detect_skill_call(msgs) == "deploy"

    def test_returns_none_for_non_skill_tool_call(self) -> None:
        msgs: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": "Bash", "arguments": '{"command": "ls"}'}},
                ],
            },
            {"role": "tool", "content": "file.txt", "tool_call_id": "tc_1"},
        ]
        assert _detect_skill_call(msgs) is None

    def test_returns_none_when_user_message_follows(self) -> None:
        """User message after the tool message means skill was already injected."""
        msgs: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": self._skill_name(), "arguments": '{"skill": "commit"}'}},
                ],
            },
            {"role": "tool", "content": "Launching skill: commit", "tool_call_id": "tc_1"},
            {"role": "user", "content": "<skill content already injected>"},
        ]
        assert _detect_skill_call(msgs) is None

    def test_handles_invalid_json_arguments_gracefully(self) -> None:
        """Malformed JSON in tool_calls.function.arguments must not raise."""
        msgs: list[dict[str, Any]] = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "function": {"name": self._skill_name(), "arguments": "not-json"}},
                ],
            },
            {"role": "tool", "content": "...", "tool_call_id": "tc_1"},
        ]
        # Should return None (no "skill" key in empty fallback dict)
        assert _detect_skill_call(msgs) is None


# ---------------------------------------------------------------------------
# AgentMiddleware.awrap_tool_call — permission gating
# ---------------------------------------------------------------------------


class _DenyRule(SafetyRule):
    """Denies every tool call."""

    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision | None:
        return PermissionDecision(result=PermissionResult.DENIED, reason="blocked by test rule")


class _ApprovalRule(SafetyRule):
    """Requires approval for every tool call."""

    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision | None:
        return PermissionDecision(result=PermissionResult.NEEDS_APPROVAL, approval_prompt="Approve?")


class TestAwrapToolCallPermissionGating:
    """``awrap_tool_call`` enforces permission decisions from ``PermissionGate``."""

    async def test_allowed_call_invokes_handler_and_returns_result(self) -> None:
        mw = _make_middleware()
        expected = ToolMessage(content="success", tool_call_id="tc_1")
        handler = AsyncMock(return_value=expected)
        request = _make_request()

        result = await mw.awrap_tool_call(request, handler)

        handler.assert_awaited_once()
        assert result is expected

    async def test_denied_call_returns_error_message_without_handler(self) -> None:
        gate = _make_gate_with_rule(_DenyRule())
        mw = _make_middleware(gate=gate)
        handler = AsyncMock()
        request = _make_request("bash")

        result = await mw.awrap_tool_call(request, handler)

        handler.assert_not_awaited()
        assert isinstance(result, ToolMessage)
        assert "blocked by test rule" in result.content

    async def test_denied_response_contains_permission_denied_prefix(self) -> None:
        gate = _make_gate_with_rule(_DenyRule())
        mw = _make_middleware(gate=gate)
        request = _make_request("bash")
        handler = AsyncMock()

        result = await mw.awrap_tool_call(request, handler)

        assert isinstance(result, ToolMessage)
        assert isinstance(result.content, str)
        assert result.content.startswith("Permission denied")

    async def test_needs_approval_without_callback_returns_error(self) -> None:
        gate = _make_gate_with_rule(_ApprovalRule())
        mw = _make_middleware(gate=gate, approval_callback=None)
        handler = AsyncMock()
        request = _make_request("read")

        result = await mw.awrap_tool_call(request, handler)

        handler.assert_not_awaited()
        assert isinstance(result, ToolMessage)
        assert isinstance(result.content, str)
        assert "requires approval" in result.content.lower()

    async def test_needs_approval_approved_by_callback_calls_handler(self) -> None:
        gate = _make_gate_with_rule(_ApprovalRule())
        callback = AsyncMock(return_value=True)
        mw = _make_middleware(gate=gate, approval_callback=callback)
        expected = ToolMessage(content="done", tool_call_id="tc_1")
        handler = AsyncMock(return_value=expected)
        request = _make_request("read")

        result = await mw.awrap_tool_call(request, handler)

        callback.assert_awaited_once()
        handler.assert_awaited_once()
        assert result is expected

    async def test_needs_approval_rejected_by_callback_returns_error(self) -> None:
        gate = _make_gate_with_rule(_ApprovalRule())
        callback = AsyncMock(return_value=False)
        mw = _make_middleware(gate=gate, approval_callback=callback)
        handler = AsyncMock()
        request = _make_request("read")

        result = await mw.awrap_tool_call(request, handler)

        handler.assert_not_awaited()
        assert isinstance(result, ToolMessage)
        assert "denied by user" in result.content
