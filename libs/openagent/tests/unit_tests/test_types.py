"""Tests for types.py — ToolResult, CLIResult, CompactionPhase, AgentContext."""

# ruff: noqa: S604

from datetime import UTC, datetime

import pytest

from openagent.mcp import McpClient
from openagent.types import (
    AgentContext,
    CLIResult,
    CompactionPhase,
    EnvironmentContext,
    GitContext,
    Skill,
    SkillCatalog,
    ToolResult,
)

from .conftest import make_tool


def _make_mcp_client(name: str, instructions: str = "") -> McpClient:
    """Create an McpClient with pre-set instructions for testing."""
    client = McpClient(name, {"type": "http", "url": "https://example.com"})
    client._instructions = instructions
    return client


class TestToolResultBool:
    """Tests for ToolResult.__bool__."""

    def test_empty_result_is_falsy(self) -> None:
        """Empty ToolResult should be falsy."""
        result = ToolResult()
        assert not result

    def test_result_with_output_is_truthy(self) -> None:
        """ToolResult with output should be truthy."""
        result = ToolResult(output="hello")
        assert result

    def test_result_with_error_is_truthy(self) -> None:
        """ToolResult with error should be truthy."""
        result = ToolResult(error="something went wrong")
        assert result

    def test_result_with_system_is_truthy(self) -> None:
        """ToolResult with system message should be truthy."""
        result = ToolResult(system="restarted")
        assert result

    def test_result_with_base64_image_is_truthy(self) -> None:
        """ToolResult with base64_image should be truthy."""
        result = ToolResult(base64_image="abc123")
        assert result

    def test_result_with_empty_strings_is_falsy(self) -> None:
        """ToolResult with empty strings is still falsy (empty string is falsy)."""
        result = ToolResult(output="", error="", system="")
        assert not result


class TestToolResultAdd:
    """Tests for ToolResult.__add__."""

    def test_add_outputs(self) -> None:
        """Adding two results with outputs concatenates them."""
        r1 = ToolResult(output="line1\n")
        r2 = ToolResult(output="line2")
        combined = r1 + r2
        assert combined.output == "line1\nline2"

    def test_add_errors(self) -> None:
        """Adding two results with errors concatenates them."""
        r1 = ToolResult(error="err1")
        r2 = ToolResult(error="err2")
        combined = r1 + r2
        assert combined.error == "err1err2"

    def test_add_system_messages(self) -> None:
        """Adding two results with system messages concatenates them."""
        r1 = ToolResult(system="msg1")
        r2 = ToolResult(system="msg2")
        combined = r1 + r2
        assert combined.system == "msg1msg2"

    def test_add_with_one_none_field(self) -> None:
        """When only one result has a field, use that field."""
        r1 = ToolResult(output="hello")
        r2 = ToolResult()
        combined = r1 + r2
        assert combined.output == "hello"
        assert combined.error is None

    def test_add_base64_images_raises(self) -> None:
        """Adding two results with base64_images raises ValueError."""
        r1 = ToolResult(base64_image="abc")
        r2 = ToolResult(base64_image="def")
        with pytest.raises(ValueError, match="Cannot combine"):
            _ = r1 + r2

    def test_add_base64_image_with_none(self) -> None:
        """Adding result with base64_image to result without is fine."""
        r1 = ToolResult(base64_image="abc")
        r2 = ToolResult(output="hello")
        combined = r1 + r2
        assert combined.base64_image == "abc"
        assert combined.output == "hello"

    def test_add_preserves_all_fields(self) -> None:
        """Adding combines all fields appropriately."""
        r1 = ToolResult(output="out1", error="err1", system="sys1")
        r2 = ToolResult(output="out2", error="err2", system="sys2")
        combined = r1 + r2
        assert combined.output == "out1out2"
        assert combined.error == "err1err2"
        assert combined.system == "sys1sys2"


class TestToolResultReplace:
    """Tests for ToolResult.replace."""

    def test_replace_output(self) -> None:
        """Replace output field."""
        original = ToolResult(output="hello")
        replaced = original.replace(output="world")
        assert replaced.output == "world"
        assert original.output == "hello"  # Original unchanged

    def test_replace_adds_new_field(self) -> None:
        """Replace can add a field that was None."""
        original = ToolResult(output="hello")
        replaced = original.replace(error="oops")
        assert replaced.output == "hello"
        assert replaced.error == "oops"

    def test_replace_multiple_fields(self) -> None:
        """Replace multiple fields at once."""
        original = ToolResult(output="hello", error="err")
        replaced = original.replace(output="world", error="fixed")
        assert replaced.output == "world"
        assert replaced.error == "fixed"

    def test_replace_with_none(self) -> None:
        """Replace a field with None."""
        original = ToolResult(output="hello", error="err")
        replaced = original.replace(error=None)
        assert replaced.output == "hello"
        assert replaced.error is None


class TestCLIResult:
    """Tests for CLIResult class."""

    def test_has_exit_code(self) -> None:
        """CLIResult has exit_code field."""
        result = CLIResult(stdout="hello", exit_code=0)
        assert result.exit_code == 0

    def test_has_stdout_stderr(self) -> None:
        """CLIResult has stdout and stderr fields."""
        result = CLIResult(stdout="output", stderr="error", exit_code=0)
        assert result.stdout == "output"
        assert result.stderr == "error"

    def test_defaults(self) -> None:
        """CLIResult has sensible defaults."""
        result = CLIResult()
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code == 0
        assert result.metadata is None

    def test_frozen_dataclass(self) -> None:
        """CLIResult is a frozen dataclass."""
        from dataclasses import FrozenInstanceError

        result = CLIResult(stdout="hello")
        with pytest.raises(FrozenInstanceError):
            result.stdout = "world"  # type: ignore[misc]


class TestToolResultToText:
    """Tests for ToolResult.to_text() — the documented formatting contract."""

    def test_output_only(self) -> None:
        assert ToolResult(output="hello").to_text() == "hello"

    def test_error_only(self) -> None:
        assert ToolResult(error="file not found").to_text() == "<error>file not found</error>"

    def test_output_and_error(self) -> None:
        result = ToolResult(output="partial", error="failed").to_text()
        assert result == "partial\n<error>failed</error>"

    def test_output_and_system(self) -> None:
        result = ToolResult(output="done", system="session restarted").to_text()
        assert result == "done\n\n<system>session restarted</system>"

    def test_empty_result(self) -> None:
        result = ToolResult().to_text()
        assert result == "<system>Tool ran without output or errors</system>"

    def test_system_only(self) -> None:
        result = ToolResult(system="session restarted").to_text()
        assert result == "<system>Tool ran without output or errors\nsession restarted</system>"

    def test_str_delegates_to_to_text(self) -> None:
        r = ToolResult(output="hello")
        assert str(r) == r.to_text()


class TestCompactionPhase:
    """Tests for CompactionPhase enum values."""

    def test_enum_values(self) -> None:
        assert CompactionPhase.NONE.value == "none"
        assert CompactionPhase.REQUESTING.value == "requesting"
        assert CompactionPhase.APPLYING.value == "applying"

    def test_string_roundtrip(self) -> None:
        for phase in CompactionPhase:
            assert CompactionPhase(phase.value) is phase

    def test_is_str_enum(self) -> None:
        assert isinstance(CompactionPhase.NONE, str)


class TestAgentContext:
    """Tests for AgentContext — the context snapshot dataclass."""

    def test_defaults_to_empty(self) -> None:
        ctx = AgentContext()
        assert ctx.tools == []
        assert ctx.skills == []
        assert ctx.mcps == []
        assert ctx.environment is None
        assert ctx.git is None

    def test_full_construction(self) -> None:
        git = GitContext(current_branch="feat", main_branch="main", status="clean", recent_commits="abc")
        ctx = AgentContext(
            tools=[make_tool("Bash")],
            skills=[Skill(name="commit", description="desc", path="/p")],
            mcps=[_make_mcp_client("gh", "GitHub API")],
            environment=EnvironmentContext(
                working_dir="/home/user",
                is_git_repo=True,
                platform="linux",
                shell="bash",
                os_version="Linux 6.1.0",
                today_date=datetime(2026, 2, 14, 10, 30, 0, tzinfo=UTC),
            ),
            git=git,
        )
        assert len(ctx.tools) == 1
        assert len(ctx.skills) == 1
        assert ctx.git is not None

    def test_tool_name_vars_builds_dict_from_tools(self) -> None:
        ctx = AgentContext(tools=[make_tool("Bash"), make_tool("Read")])
        assert ctx.tool_name_vars == {"BASH_TOOL_NAME": "Bash", "READ_TOOL_NAME": "Read"}

    def test_tool_name_vars_empty_without_tools(self) -> None:
        assert AgentContext().tool_name_vars == {}


class TestSkillCatalog:
    """Tests for the SkillCatalog protocol."""

    def test_protocol_is_runtime_checkable(self) -> None:
        class _Catalog:
            async def has(self, name: str) -> bool:
                return True

        assert isinstance(_Catalog(), SkillCatalog)
