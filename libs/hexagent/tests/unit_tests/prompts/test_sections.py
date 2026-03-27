"""Tests for prompt sections, compose, and profiles."""

# ruff: noqa: S604, S108, PLR2004, RUF005

from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from hexagent.harness.definition import AgentDefinition
from hexagent.harness.model import ModelProfile
from hexagent.mcp import McpClient
from hexagent.prompts import FRESH_SESSION, RESUMED_SESSION, SUBAGENT_SESSION, compose
from hexagent.prompts.sections import (
    agency,
    doing_tasks,
    environment,
    executing_actions_with_care,
    identity,
    mcps,
    tone_and_style,
    tool_instructions,
    using_your_tools,
)
from hexagent.types import AgentContext, EnvironmentContext

from ..conftest import STUB_PROFILE, core_tools, make_tool


def _make_mcp_client(name: str, instructions: str = "") -> McpClient:
    """Create an McpClient with pre-set instructions for testing."""
    client = McpClient(name, {"type": "http", "url": "https://example.com"})
    client._instructions = instructions
    return client


# ---------------------------------------------------------------------------
# Section functions
# ---------------------------------------------------------------------------


class TestIdentity:
    def test_includes_agent_name(self) -> None:
        result = identity(AgentContext(model=STUB_PROFILE))
        assert result is not None
        assert "HexAgent" in result


class TestDoingTasks:
    def test_includes_heading(self) -> None:
        result = doing_tasks(AgentContext(model=STUB_PROFILE))
        assert result is not None
        assert "Doing tasks" in result


class TestExecutingActionsWithCare:
    def test_includes_heading(self) -> None:
        result = executing_actions_with_care(AgentContext(model=STUB_PROFILE))
        assert result is not None
        assert "Executing actions" in result


class TestToneAndStyle:
    def test_includes_heading(self) -> None:
        result = tone_and_style(AgentContext(model=STUB_PROFILE, tools=[make_tool("Bash"), make_tool("Read")]))
        assert result is not None
        assert "Tone and style" in result

    def test_resolves_tool_name_placeholders(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=[make_tool("Bash"), make_tool("Read")])
        result = tone_and_style(ctx)
        assert result is not None
        assert "${BASH_TOOL_NAME}" not in result
        assert "${READ_TOOL_NAME}" not in result


class TestAgency:
    def test_includes_heading(self) -> None:
        result = agency(AgentContext(model=STUB_PROFILE))
        assert result is not None
        assert "Agency" in result


class TestUsingYourTools:
    def test_returns_none_without_tools(self) -> None:
        assert using_your_tools(AgentContext(model=STUB_PROFILE)) is None

    def test_includes_heading_with_tools(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools())
        result = using_your_tools(ctx)
        assert result is not None
        assert "Using your tools" in result

    def test_resolves_tool_name_placeholders(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools())
        result = using_your_tools(ctx)
        assert result is not None
        for name in ("Read", "Edit", "Write"):
            assert name in result
        assert "${READ_TOOL_NAME}" not in result


class TestToolInstructions:
    def test_returns_none_without_tools(self) -> None:
        assert tool_instructions(AgentContext(model=STUB_PROFILE)) is None

    def test_renders_tool_heading_per_tool(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools())
        result = tool_instructions(ctx)
        assert result is not None
        assert "# Tools" in result
        assert "## Bash" in result
        assert "## Read" in result
        assert "---" in result

    def test_includes_supplementary_fragments(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools())
        result = tool_instructions(ctx)
        assert result is not None
        assert "Committing changes with git" in result

    def test_resolves_all_tool_name_cross_references(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools())
        result = tool_instructions(ctx)
        assert result is not None
        for name in ("GLOB", "GREP", "READ", "EDIT", "WRITE"):
            assert f"${{{name}_TOOL_NAME}}" not in result

    def test_resolves_git_parallel_note(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools())
        result = tool_instructions(ctx)
        assert result is not None
        assert "${GIT_PARALLEL_NOTE}" not in result
        assert "run multiple tool calls in parallel" in result

    def test_skips_tool_without_fragment_or_instruction(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=[make_tool("nonexistent_tool_xyz")])
        result = tool_instructions(ctx)
        assert result is not None
        assert "nonexistent_tool_xyz" not in result

    def test_falls_back_to_inline_instruction(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=[make_tool("custom", instruction="Custom inline docs.")])
        result = tool_instructions(ctx)
        assert result is not None
        assert "## custom" in result
        assert "Custom inline docs." in result

    def test_resolves_date_placeholders(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=[make_tool("WebSearch")])
        result = tool_instructions(ctx)
        assert result is not None
        assert "${CURRENT_DATE}" not in result
        today = date.today()  # noqa: DTZ011
        assert today.isoformat() in result


class TestMcps:
    def test_returns_none_when_empty(self) -> None:
        assert mcps(AgentContext(model=STUB_PROFILE)) is None

    def test_formats_mcp_entry(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, mcps=[_make_mcp_client("github", "GitHub API")])
        result = mcps(ctx)
        assert result is not None
        assert "# MCP Servers" in result
        assert "**github**" in result


class TestEnvironment:
    def test_returns_none_when_empty(self) -> None:
        assert environment(AgentContext(model=STUB_PROFILE)) is None

    def test_loads_md_and_substitutes_vars(self) -> None:
        env = EnvironmentContext(
            working_dir="/home/user",
            is_git_repo=True,
            platform="linux",
            shell="bash",
            os_version="Ubuntu 22.04",
            today_date=datetime(2026, 2, 14, 10, 30, 0, tzinfo=UTC),
        )
        mock_model = MagicMock()
        mock_model.model_name = "gpt-5.2"
        profile = ModelProfile(model=mock_model, compaction_threshold=100_000)
        ctx = AgentContext(model=profile, environment=env)
        result = environment(ctx)
        assert result is not None
        assert "Environment" in result
        assert "/home/user" in result
        assert "linux" in result
        assert "gpt-5.2" in result
        assert "true" in result
        assert "Sat Feb 14, 2026" in result


# ---------------------------------------------------------------------------
# Compose and profiles
# ---------------------------------------------------------------------------


class TestCompose:
    def test_empty_profile_returns_empty_string(self) -> None:
        assert compose([], AgentContext(model=STUB_PROFILE)) == ""

    def test_filters_none_sections(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE)  # no tools → using_your_tools returns None
        result = compose([identity, using_your_tools], ctx)
        assert "HexAgent" in result
        assert "Using your tools" not in result

    def test_joins_sections_with_double_newline(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, mcps=[_make_mcp_client("github", "GitHub API")])
        result = compose([identity, mcps], ctx)
        parts = result.split("\n\n")
        assert len(parts) >= 2

    def test_fresh_session_includes_tools(self) -> None:
        result = compose(FRESH_SESSION, AgentContext(model=STUB_PROFILE, tools=core_tools()))
        assert "HexAgent" in result
        assert "# Tools" in result
        assert "## Bash" in result

    def test_section_ordering_matches_profile(self) -> None:
        ctx = AgentContext(
            model=STUB_PROFILE,
            tools=core_tools(),
            mcps=[_make_mcp_client("github", "GitHub API")],
        )
        result = compose(FRESH_SESSION, ctx)
        identity_pos = result.index("HexAgent")
        tools_pos = result.index("# Tools")
        mcps_pos = result.index("# MCP Servers")
        assert identity_pos < tools_pos < mcps_pos

    def test_custom_profile_only_includes_specified_sections(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, mcps=[_make_mcp_client("github", "GitHub API")])
        result = compose([identity, mcps], ctx)
        assert "HexAgent" in result
        assert "github" in result
        assert "Doing tasks" not in result

    def test_resumed_session_matches_fresh(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools())
        assert compose(FRESH_SESSION, ctx) == compose(RESUMED_SESSION, ctx)


# ---------------------------------------------------------------------------
# SUBAGENT_SESSION profile
# ---------------------------------------------------------------------------


class TestSubagentSession:
    def test_excludes_root_sections(self) -> None:
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools() + [make_tool("Agent"), make_tool("TaskOutput")])
        result = compose(SUBAGENT_SESSION, ctx)
        # Identity section starts with "You are HexAgent"
        assert "You are HexAgent" not in result
        assert "## Agency" not in result
        assert "## Doing tasks" not in result
        assert "## Executing actions with care" not in result

    def test_includes_environment_and_tools(self) -> None:
        env = EnvironmentContext(
            working_dir="/tmp",
            is_git_repo=False,
            platform="linux",
            shell="bash",
            os_version="Ubuntu 22.04",
            today_date=datetime(2026, 2, 14, 10, 30, 0, tzinfo=UTC),
        )
        ctx = AgentContext(model=STUB_PROFILE, tools=core_tools() + [make_tool("Agent"), make_tool("TaskOutput")], environment=env)
        result = compose(SUBAGENT_SESSION, ctx)
        assert "# Tools" in result
        assert "## Bash" in result
        assert "/tmp" in result


# ---------------------------------------------------------------------------
# AVAILABLE_AGENTS template variable
# ---------------------------------------------------------------------------


class TestAvailableAgents:
    def test_substituted_in_task_instruction(self) -> None:
        agents = {
            "explorer": AgentDefinition(description="Explore codebase"),
            "planner": AgentDefinition(description="Plan implementations"),
        }
        ctx = AgentContext(
            model=STUB_PROFILE,
            tools=[make_tool("Agent"), make_tool("TaskOutput")],
            agents=agents,
        )
        result = tool_instructions(ctx)
        assert result is not None
        assert "${AVAILABLE_AGENTS}" not in result
        assert "general-purpose" in result
        assert "explorer" in result
        assert "Explore codebase" in result
        assert "planner" in result
        assert "Plan implementations" in result

    def test_with_no_definitions_shows_general_purpose(self) -> None:
        ctx = AgentContext(
            model=STUB_PROFILE,
            tools=[make_tool("Agent"), make_tool("TaskOutput")],
            agents={},
        )
        result = tool_instructions(ctx)
        assert result is not None
        assert "general-purpose" in result
