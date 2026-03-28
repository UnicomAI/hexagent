# ruff: noqa: PLR2004
"""Tests for agent factory helper functions and Agent lifecycle."""

from __future__ import annotations

from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from clawwork.harness.definition import AgentDefinition
from clawwork.harness.model import _FALLBACK_COMPACTION_THRESHOLD, ModelProfile
from clawwork.langchain.agent import Agent, _resolve_to_profile, _validate_agent_tools
from clawwork.tasks import TaskRegistry
from tests.unit_tests.conftest import make_tool

# ---------------------------------------------------------------------------
# _validate_agent_tools
# ---------------------------------------------------------------------------


class TestValidateAgentTools:
    """Tests for _validate_agent_tools()."""

    def test_valid_tools_pass(self) -> None:
        tools = [make_tool("Bash"), make_tool("Read")]
        agents = {"helper": AgentDefinition(description="h", tools=("Bash",))}

        _validate_agent_tools(agents, tools)  # should not raise

    def test_unknown_tool_raises(self) -> None:
        tools = [make_tool("Bash")]
        agents = {"helper": AgentDefinition(description="h", tools=("NoSuchTool",))}

        with pytest.raises(ValueError, match="unknown tool 'NoSuchTool'"):
            _validate_agent_tools(agents, tools)

    def test_forbidden_agent_tool_raises(self) -> None:
        tools = [make_tool("Bash"), make_tool("Agent")]
        agents = {"helper": AgentDefinition(description="h", tools=("Agent",))}

        with pytest.raises(ValueError, match="subagents cannot use 'Agent'"):
            _validate_agent_tools(agents, tools)

    def test_empty_definitions_pass(self) -> None:
        tools = [make_tool("Bash")]

        _validate_agent_tools({}, tools)  # should not raise

    def test_multiple_agents_all_validated(self) -> None:
        """Validation checks all definitions, not just the first."""
        tools = [make_tool("Bash")]
        agents = {
            "ok_agent": AgentDefinition(description="ok", tools=("Bash",)),
            "bad_agent": AgentDefinition(description="bad", tools=("Missing",)),
        }

        with pytest.raises(ValueError, match="bad_agent"):
            _validate_agent_tools(agents, tools)


# ---------------------------------------------------------------------------
# _resolve_to_profile
# ---------------------------------------------------------------------------


def _stub_model(name: str = "stub-model") -> MagicMock:
    m = MagicMock()
    m.model_name = name
    return m


class TestResolveToProfile:
    """Tests for _resolve_to_profile()."""

    def test_model_profile_passthrough(self) -> None:
        """Profile with threshold set is returned as-is."""
        profile = ModelProfile(model=_stub_model(), compaction_threshold=50_000)
        result = _resolve_to_profile(profile)

        assert result is profile
        assert result.compaction_threshold == 50_000

    def test_missing_threshold_gets_fallback(self) -> None:
        """No context_window + no threshold -> fallback applied."""
        profile = ModelProfile(model=_stub_model())
        assert profile.compaction_threshold is None

        result = _resolve_to_profile(profile)

        assert result.compaction_threshold == _FALLBACK_COMPACTION_THRESHOLD

    def test_context_window_derives_threshold(self) -> None:
        """context_window set -> threshold derived by ModelProfile, no fallback."""
        profile = ModelProfile(model=_stub_model(), context_window=100_000)
        result = _resolve_to_profile(profile)

        # ModelProfile.__post_init__ derives 0.75 * 100_000 = 75_000
        assert result.compaction_threshold == 75_000
        assert result is profile  # no replacement needed

    def test_base_chat_model_wrapped(self) -> None:
        """Raw BaseChatModel gets wrapped in ModelProfile."""
        mock_model = _stub_model()
        result = _resolve_to_profile(mock_model)

        assert isinstance(result, ModelProfile)
        assert result.model is mock_model
        # No context_window -> fallback threshold applied
        assert result.compaction_threshold == _FALLBACK_COMPACTION_THRESHOLD

    def test_string_model_resolved(self) -> None:
        """String input calls init_chat_model."""
        mock_model = _stub_model("resolved-model")
        with patch("clawwork.langchain.agent.init_chat_model", return_value=mock_model) as mock_init:
            result = _resolve_to_profile("some-model-name")

        mock_init.assert_called_once_with("some-model-name")
        assert isinstance(result, ModelProfile)
        assert result.model is mock_model


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------


class TestAgentLifecycle:
    """Tests for Agent.aclose() and context manager."""

    async def test_aclose_cancels_registry_and_closes_resources(self) -> None:
        registry = TaskRegistry()
        resources = AsyncExitStack()
        agent = Agent(
            context=MagicMock(),
            graph=MagicMock(),
            resources=resources,
            system_prompt="test",
            task_registry=registry,
        )

        # Spy on the methods
        registry.cancel_all = AsyncMock()  # type: ignore[method-assign]
        resources.aclose = AsyncMock()  # type: ignore[method-assign]

        await agent.aclose()

        registry.cancel_all.assert_awaited_once()
        resources.aclose.assert_awaited_once()

    async def test_aclose_suppresses_runtime_error(self) -> None:
        """Cross-task RuntimeError from AsyncExitStack is caught."""
        registry = TaskRegistry()
        resources = AsyncExitStack()
        agent = Agent(
            context=MagicMock(),
            graph=MagicMock(),
            resources=resources,
            system_prompt="test",
            task_registry=registry,
        )

        registry.cancel_all = AsyncMock()  # type: ignore[method-assign]
        resources.aclose = AsyncMock(side_effect=RuntimeError("cross-task"))  # type: ignore[method-assign]

        # Should not raise
        await agent.aclose()

    async def test_context_manager_delegates_to_aclose(self) -> None:
        registry = TaskRegistry()
        resources = AsyncExitStack()
        agent = Agent(
            context=MagicMock(),
            graph=MagicMock(),
            resources=resources,
            system_prompt="test",
            task_registry=registry,
        )
        agent.aclose = AsyncMock()  # type: ignore[method-assign]

        async with agent:
            pass

        agent.aclose.assert_awaited_once()
