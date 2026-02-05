"""Tests for AgentMiddleware.

Tests the middleware integration with CompactionController:
1. Phase transitions via aafter_model / after_model
2. Context updates via abefore_model / before_model
3. Token counting and threshold detection
4. Message rebuilding with Overwrite
5. Sync and async hooks parity
"""

# ruff: noqa: PLR2004
# mypy: disable-error-code="arg-type"

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Overwrite

from openagent.langchain.middleware import AgentMiddleware, _estimate_tokens
from openagent.runtime import CapabilityRegistry, CompactionPhase, PermissionGate

if TYPE_CHECKING:
    from collections.abc import Sequence

    from langchain_core.messages import BaseMessage


# --- Constants ---

TEST_COMPACTION_PROMPT = "Please summarize what you have done so far."
TEST_SUMMARY_TEMPLATE = "## Previous Conversation Summary\n\n{summary_content}\n\nPlease continue from where we left off."

# --- Fixtures ---


@pytest.fixture
def registry() -> CapabilityRegistry:
    return CapabilityRegistry()


@pytest.fixture
def permission_gate() -> PermissionGate:
    return PermissionGate()


@pytest.fixture
def middleware(registry: CapabilityRegistry, permission_gate: PermissionGate) -> AgentMiddleware:
    return AgentMiddleware(
        registry=registry,
        system_prompt="Test prompt",
        permission_gate=permission_gate,
        compaction_prompt=TEST_COMPACTION_PROMPT,
        summary_rebuild_template=TEST_SUMMARY_TEMPLATE,
        compaction_threshold=100,
    )


@pytest.fixture
def state_none() -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="test")],
        "compaction_phase": CompactionPhase.NONE,
    }


@pytest.fixture
def state_requesting() -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="test"), AIMessage(content="response")],
        "compaction_phase": CompactionPhase.REQUESTING,
    }


@pytest.fixture
def state_applying() -> dict[str, Any]:
    return {
        "messages": [
            HumanMessage(content="original"),
            HumanMessage(content="compaction prompt"),
            AIMessage(content="This is the summary of our conversation."),
        ],
        "compaction_phase": CompactionPhase.APPLYING,
    }


# --- Phase transition tests (aafter_model) ---


class TestCompactionPhaseTransitions:
    """Test phase transitions in aafter_model / after_model."""

    async def test_none_to_requesting_when_threshold_exceeded(
        self,
        middleware: AgentMiddleware,
    ) -> None:
        state = {
            "messages": [HumanMessage(content="x" * 500), AIMessage(content="response")],
            "compaction_phase": CompactionPhase.NONE,
        }

        result = await middleware.aafter_model(state)

        assert result is not None
        assert result["compaction_phase"] == CompactionPhase.REQUESTING
        assert result["jump_to"] == "model"

    async def test_none_stays_none_below_threshold(
        self,
        middleware: AgentMiddleware,
        state_none: dict[str, Any],
    ) -> None:
        result = await middleware.aafter_model(state_none)
        assert result is None

    async def test_requesting_to_applying(
        self,
        middleware: AgentMiddleware,
        state_requesting: dict[str, Any],
    ) -> None:
        result = await middleware.aafter_model(state_requesting)

        assert result is not None
        assert result["compaction_phase"] == CompactionPhase.APPLYING
        assert result["jump_to"] == "model"

    async def test_applying_returns_none_in_after_model(
        self,
        middleware: AgentMiddleware,
        state_applying: dict[str, Any],
    ) -> None:
        result = await middleware.aafter_model(state_applying)
        assert result is None


# --- Before model tests ---


class TestBeforeModelPhases:
    """Test abefore_model / before_model hook behavior."""

    async def test_requesting_injects_compaction_prompt(
        self,
        middleware: AgentMiddleware,
        state_requesting: dict[str, Any],
    ) -> None:
        result = await middleware.abefore_model(state_requesting)

        assert result is not None
        messages = result["messages"]
        assert len(messages) == 3
        assert isinstance(messages[-1], HumanMessage)
        assert messages[-1].content == TEST_COMPACTION_PROMPT

    async def test_applying_rebuilds_with_overwrite(
        self,
        middleware: AgentMiddleware,
        state_applying: dict[str, Any],
    ) -> None:
        result = await middleware.abefore_model(state_applying)

        assert result is not None
        assert isinstance(result["messages"], Overwrite)
        assert result["compaction_phase"] == CompactionPhase.NONE

        rebuilt = result["messages"].value
        assert len(rebuilt) == 1
        assert isinstance(rebuilt[0], HumanMessage)
        content = rebuilt[0].content
        assert isinstance(content, str)
        assert "summary" in content.lower()

    async def test_none_returns_none(
        self,
        middleware: AgentMiddleware,
        state_none: dict[str, Any],
    ) -> None:
        result = await middleware.abefore_model(state_none)
        assert result is None


# --- Token counting tests ---


class TestTokenCounting:
    """Test threshold detection and custom counters."""

    def test_estimate_tokens_string_content(self) -> None:
        messages = [HumanMessage(content="Hello world")]  # 11 chars
        tokens = _estimate_tokens(messages)
        assert tokens == 2  # 11 // 4

    def test_estimate_tokens_list_content(self) -> None:
        messages = [
            AIMessage(content=[{"text": "Hello"}, {"text": "World"}]),  # 10 chars
        ]
        tokens = _estimate_tokens(messages)
        assert tokens == 2  # 10 // 4

    def test_estimate_tokens_mixed_content(self) -> None:
        messages = [
            HumanMessage(content="Test"),  # 4 chars
            AIMessage(content=[{"text": "Response"}]),  # 8 chars
        ]
        tokens = _estimate_tokens(messages)
        assert tokens == 3  # 12 // 4

    def test_custom_token_counter(
        self,
        registry: CapabilityRegistry,
        permission_gate: PermissionGate,
    ) -> None:
        def fixed_counter(_messages: Sequence[BaseMessage]) -> int:
            return 1000

        mw = AgentMiddleware(
            registry=registry,
            system_prompt="Test",
            permission_gate=permission_gate,
            compaction_prompt=TEST_COMPACTION_PROMPT,
            summary_rebuild_template=TEST_SUMMARY_TEMPLATE,
            compaction_threshold=500,
            count_tokens=fixed_counter,
        )

        state = {
            "messages": [HumanMessage(content="hi"), AIMessage(content="hello")],
            "compaction_phase": CompactionPhase.NONE,
        }

        # Custom counter should make after_model trigger compaction
        # even with short messages
        result = mw.after_model(state)
        assert result is not None
        assert result["compaction_phase"] == CompactionPhase.REQUESTING


# --- Message rebuilding tests ---


class TestMessageRebuilding:
    """Test summary extraction and Overwrite usage."""

    def test_rebuild_extracts_string_content(
        self,
        middleware: AgentMiddleware,
    ) -> None:
        messages = [
            HumanMessage(content="original"),
            HumanMessage(content="compaction prompt"),
            AIMessage(content="This is my summary of the conversation."),
        ]

        rebuilt = middleware._rebuild_with_summary(messages)

        assert len(rebuilt) == 1
        assert isinstance(rebuilt[0], HumanMessage)
        assert "This is my summary of the conversation" in rebuilt[0].content

    def test_rebuild_extracts_content_blocks(
        self,
        middleware: AgentMiddleware,
    ) -> None:
        messages = [
            HumanMessage(content="original"),
            AIMessage(content=[{"text": "Block 1 "}, {"text": "Block 2"}]),
        ]

        rebuilt = middleware._rebuild_with_summary(messages)

        assert len(rebuilt) == 1
        assert "Block 1" in rebuilt[0].content
        assert "Block 2" in rebuilt[0].content

    def test_rebuild_returns_human_message_with_summary(
        self,
        middleware: AgentMiddleware,
    ) -> None:
        messages = [
            HumanMessage(content="original"),
            AIMessage(content="Summary content here"),
        ]

        rebuilt = middleware._rebuild_with_summary(messages)

        assert len(rebuilt) == 1
        assert isinstance(rebuilt[0], HumanMessage)
        assert "Previous Conversation Summary" in rebuilt[0].content
        assert "Summary content here" in rebuilt[0].content
        assert "continue from where we left off" in rebuilt[0].content

    def test_rebuild_handles_empty_content(
        self,
        middleware: AgentMiddleware,
    ) -> None:
        messages = [
            HumanMessage(content="original"),
            AIMessage(content=""),
        ]

        rebuilt = middleware._rebuild_with_summary(messages)

        assert len(rebuilt) == 1
        assert "Previous Conversation Summary" in rebuilt[0].content


# --- Sync/async parity tests ---


class TestSyncAsyncParity:
    """Ensure sync and async hooks behave identically."""

    async def test_before_model_parity_requesting(
        self,
        middleware: AgentMiddleware,
        state_requesting: dict[str, Any],
    ) -> None:
        sync_result = middleware.before_model(state_requesting)
        async_result = await middleware.abefore_model(state_requesting)

        assert sync_result is not None
        assert async_result is not None
        assert len(sync_result["messages"]) == len(async_result["messages"])
        assert sync_result["messages"][-1].content == async_result["messages"][-1].content

    async def test_before_model_parity_applying(
        self,
        middleware: AgentMiddleware,
        state_applying: dict[str, Any],
    ) -> None:
        sync_result = middleware.before_model(state_applying)
        async_result = await middleware.abefore_model(state_applying)

        assert sync_result is not None
        assert async_result is not None
        assert isinstance(sync_result["messages"], Overwrite)
        assert isinstance(async_result["messages"], Overwrite)
        assert sync_result["compaction_phase"] == CompactionPhase.NONE
        assert async_result["compaction_phase"] == CompactionPhase.NONE

    async def test_before_model_parity_none(
        self,
        middleware: AgentMiddleware,
        state_none: dict[str, Any],
    ) -> None:
        sync_result = middleware.before_model(state_none)
        async_result = await middleware.abefore_model(state_none)

        assert sync_result is None
        assert async_result is None

    async def test_after_model_parity_threshold_exceeded(
        self,
        middleware: AgentMiddleware,
    ) -> None:
        state = {
            "messages": [HumanMessage(content="x" * 500), AIMessage(content="response")],
            "compaction_phase": CompactionPhase.NONE,
        }

        sync_result = middleware.after_model(state)
        async_result = await middleware.aafter_model(state)

        assert sync_result is not None
        assert async_result is not None
        assert sync_result["compaction_phase"] == async_result["compaction_phase"]
        assert sync_result["jump_to"] == async_result["jump_to"]

    async def test_after_model_parity_below_threshold(
        self,
        middleware: AgentMiddleware,
        state_none: dict[str, Any],
    ) -> None:
        sync_result = middleware.after_model(state_none)
        async_result = await middleware.aafter_model(state_none)

        assert sync_result is None
        assert async_result is None

    async def test_after_model_parity_requesting(
        self,
        middleware: AgentMiddleware,
        state_requesting: dict[str, Any],
    ) -> None:
        sync_result = middleware.after_model(state_requesting)
        async_result = await middleware.aafter_model(state_requesting)

        assert sync_result is not None
        assert async_result is not None
        assert sync_result["compaction_phase"] == CompactionPhase.APPLYING
        assert async_result["compaction_phase"] == CompactionPhase.APPLYING


# --- Custom compaction prompt tests ---


class TestCustomCompactionPrompt:
    """Test custom compaction prompt configuration."""

    async def test_custom_prompt_used_in_requesting_phase(
        self,
        registry: CapabilityRegistry,
        permission_gate: PermissionGate,
    ) -> None:
        custom_prompt = "Please provide a brief summary of our conversation."

        mw = AgentMiddleware(
            registry=registry,
            system_prompt="Test",
            permission_gate=permission_gate,
            compaction_prompt=custom_prompt,
            summary_rebuild_template=TEST_SUMMARY_TEMPLATE,
        )

        state = {
            "messages": [HumanMessage(content="test")],
            "compaction_phase": CompactionPhase.REQUESTING,
        }

        result = await mw.abefore_model(state)

        assert result is not None
        assert result["messages"][-1].content == custom_prompt

    async def test_configured_prompt_used_in_requesting_phase(
        self,
        middleware: AgentMiddleware,
        state_requesting: dict[str, Any],
    ) -> None:
        result = await middleware.abefore_model(state_requesting)

        assert result is not None
        assert result["messages"][-1].content == TEST_COMPACTION_PROMPT
