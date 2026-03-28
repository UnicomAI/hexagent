"""Tests for subagent helper and LangChainSubagentRunner."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

from clawwork.harness.definition import AgentDefinition
from clawwork.langchain.subagent import LangChainSubagentRunner, _extract_final_output
from tests.unit_tests.conftest import STUB_PROFILE, make_tool

# ---------------------------------------------------------------------------
# _extract_final_output
# ---------------------------------------------------------------------------


class TestExtractFinalOutput:
    """Tests for _extract_final_output()."""

    def test_string_content(self) -> None:
        msgs: list[Any] = [AIMessage(content="hello world")]
        assert _extract_final_output(msgs) == "hello world"

    def test_list_content_blocks(self) -> None:
        msgs: list[Any] = [AIMessage(content=[{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}])]
        assert _extract_final_output(msgs) == "part1part2"

    def test_mixed_blocks_with_non_dict(self) -> None:
        msgs: list[Any] = [AIMessage(content=[{"type": "text", "text": "a"}, "raw_string"])]
        assert _extract_final_output(msgs) == "araw_string"

    def test_no_ai_messages_returns_empty(self) -> None:
        msgs: list[Any] = [HumanMessage(content="question")]
        assert _extract_final_output(msgs) == ""

    def test_empty_list_returns_empty(self) -> None:
        assert _extract_final_output([]) == ""

    def test_multiple_ai_messages_takes_last(self) -> None:
        msgs: list[Any] = [
            AIMessage(content="first"),
            HumanMessage(content="follow-up"),
            AIMessage(content="second"),
        ]
        assert _extract_final_output(msgs) == "second"


# ---------------------------------------------------------------------------
# LangChainSubagentRunner
# ---------------------------------------------------------------------------


def _make_runner(
    *,
    tools: list[Any] | None = None,
    definitions: dict[str, AgentDefinition] | None = None,
    resolved_models: dict[str, Any] | None = None,
) -> LangChainSubagentRunner:
    """Create a runner with minimal dependencies."""
    return LangChainSubagentRunner(
        default_model=STUB_PROFILE,
        base_tools=tools or [make_tool("Bash"), make_tool("Read")],
        definitions=definitions or {},
        resolved_models=resolved_models or {},
        mcps=[],
        skills=[],
        skill_resolver=None,
        environment_resolver=MagicMock(),
        environment=MagicMock(),
        permission_gate=MagicMock(),
    )


class TestSubagentRunnerGetDefinition:
    """Tests for get_definition()."""

    def test_returns_known_definition(self) -> None:
        defn = AgentDefinition(description="helper")
        runner = _make_runner(definitions={"helper": defn})

        assert runner.get_definition("helper") is defn

    def test_returns_none_for_unknown(self) -> None:
        runner = _make_runner()

        assert runner.get_definition("nonexistent") is None


class TestSubagentRunnerConstruction:
    """Tests for runner construction logic (tool filtering, model selection)."""

    def test_stores_base_tools(self) -> None:
        tools = [make_tool("Bash"), make_tool("Read"), make_tool("Write")]
        runner = _make_runner(tools=tools)

        assert len(runner._base_tools) == len(tools)

    def test_definitions_are_copied(self) -> None:
        """Runner stores a copy, not a reference."""
        original: dict[str, AgentDefinition] = {"a": AgentDefinition(description="a")}
        runner = _make_runner(definitions=original)

        original["b"] = AgentDefinition(description="b")
        assert "b" not in runner._definitions
