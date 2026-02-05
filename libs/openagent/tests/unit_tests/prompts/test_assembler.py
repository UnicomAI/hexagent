"""Tests for SystemPromptAssembler."""

# ruff: noqa: ARG002, RUF012

from pydantic import BaseModel

from openagent.prompts.assembler import (
    AssemblerContext,
    FragmentRef,
    SystemPromptAssembler,
    _has_environment,
    _has_mcps,
    _has_skills,
    _has_tools,
    _has_user_instructions,
)
from openagent.prompts.library import PromptLibrary
from openagent.tools.base import BaseAgentTool
from openagent.types import MCPServer, Skill, ToolResult


class MockParams(BaseModel):
    """Mock params for testing."""


class MockTool(BaseAgentTool[MockParams]):
    """Mock tool for testing."""

    name = "bash"
    description = "Execute shell commands"
    args_schema = MockParams

    async def execute(self, params: MockParams) -> ToolResult:
        return ToolResult(output="mock")


class AnotherTool(BaseAgentTool[MockParams]):
    """Another mock tool for testing."""

    name = "read"
    description = "Read files"
    args_schema = MockParams

    async def execute(self, params: MockParams) -> ToolResult:
        return ToolResult(output="mock")


class TestRecipe:
    """Tests for RECIPE structure."""

    def test_recipe_is_list(self) -> None:
        """Test RECIPE is a list of FragmentRef."""
        assert isinstance(SystemPromptAssembler.RECIPE, list)
        assert all(isinstance(ref, FragmentRef) for ref in SystemPromptAssembler.RECIPE)

    def test_recipe_has_expected_fragments(self) -> None:
        """Test RECIPE contains expected fragment keys."""
        keys = [ref.key for ref in SystemPromptAssembler.RECIPE]
        assert "system/base" in keys
        assert "system/tools" in keys
        assert "system/skills" in keys
        assert "system/mcps" in keys
        assert "system/environment" in keys
        assert "system/user_instructions" in keys

    def test_recipe_base_has_no_condition(self) -> None:
        """Test system/base has no condition (always included)."""
        base_ref = SystemPromptAssembler.RECIPE[0]
        assert base_ref.key == "system/base"
        assert base_ref.condition is None


class TestConditions:
    """Tests for condition functions."""

    def test_has_tools_true(self) -> None:
        ctx = AssemblerContext(tools=[MockTool()])
        assert _has_tools(ctx) is True

    def test_has_tools_false(self) -> None:
        ctx = AssemblerContext()
        assert _has_tools(ctx) is False

    def test_has_skills_true(self) -> None:
        ctx = AssemblerContext(skills=[Skill(name="s", description="d")])
        assert _has_skills(ctx) is True

    def test_has_skills_false(self) -> None:
        ctx = AssemblerContext()
        assert _has_skills(ctx) is False

    def test_has_mcps_true(self) -> None:
        ctx = AssemblerContext(mcps=[MCPServer(name="m", description="d")])
        assert _has_mcps(ctx) is True

    def test_has_mcps_false(self) -> None:
        ctx = AssemblerContext()
        assert _has_mcps(ctx) is False

    def test_has_environment_true(self) -> None:
        ctx = AssemblerContext(environment={"key": "value"})
        assert _has_environment(ctx) is True

    def test_has_environment_false(self) -> None:
        ctx = AssemblerContext()
        assert _has_environment(ctx) is False

    def test_has_user_instructions_true(self) -> None:
        ctx = AssemblerContext(user_instructions="Do something")
        assert _has_user_instructions(ctx) is True

    def test_has_user_instructions_false_none(self) -> None:
        ctx = AssemblerContext()
        assert _has_user_instructions(ctx) is False

    def test_has_user_instructions_false_empty(self) -> None:
        ctx = AssemblerContext(user_instructions="")
        assert _has_user_instructions(ctx) is False


class TestAssemble:
    """Tests for assemble() method."""

    def test_assemble_base_only(self) -> None:
        """Test assembling with only base prompt."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(library=library)
        assert "OpenAgent" in result

    def test_assemble_with_tools_includes_instructions(self) -> None:
        """Test assembling with tools includes instruction content from .md files."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        tools = [MockTool(), AnotherTool()]
        result = assembler.assemble(library=library, tools=tools)
        assert "# Tools" in result
        assert "## bash" in result
        assert "## read" in result
        assert library.get("tools/bash") in result
        assert library.get("tools/read") in result
        assert "---" in result

    def test_assemble_with_skills(self) -> None:
        """Test assembling with skills."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        skills = [
            Skill(name="commit", description="Create git commits"),
            Skill(name="review", description="Review code changes"),
        ]
        result = assembler.assemble(library=library, skills=skills)
        assert "## Skills" in result
        assert "**commit**" in result
        assert "Create git commits" in result

    def test_assemble_with_mcps(self) -> None:
        """Test assembling with MCP servers."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        mcps = [MCPServer(name="context7", description="Documentation lookup")]
        result = assembler.assemble(library=library, mcps=mcps)
        assert "## MCP Servers" in result
        assert "**context7**" in result

    def test_assemble_with_environment(self) -> None:
        """Test assembling with environment context."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(
            library=library,
            environment={"platform": "darwin", "cwd": "/home/user"},
        )
        assert "## Environment" in result
        assert "platform: darwin" in result
        assert "cwd: /home/user" in result

    def test_assemble_with_user_instructions(self) -> None:
        """Test assembling with user instructions."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(
            library=library,
            user_instructions="Focus on Python code.",
        )
        assert "## User Instructions" in result
        assert "Focus on Python code." in result

    def test_assemble_respects_order(self) -> None:
        """Test sections appear in RECIPE order."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(
            library=library,
            tools=[MockTool()],
            skills=[Skill(name="s1", description="d1")],
            mcps=[MCPServer(name="m1", description="d1")],
            environment={"key": "ENV_MARKER"},
            user_instructions="USER_MARKER",
        )
        base_pos = result.index("OpenAgent")
        tools_pos = result.index("# Tools")
        skills_pos = result.index("## Skills")
        mcps_pos = result.index("## MCP Servers")
        env_pos = result.index("ENV_MARKER")
        user_pos = result.index("USER_MARKER")

        assert base_pos < tools_pos
        assert tools_pos < skills_pos
        assert skills_pos < mcps_pos
        assert mcps_pos < env_pos
        assert env_pos < user_pos

    def test_assemble_skips_none_sections(self) -> None:
        """Test None sections are skipped."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(
            library=library,
            user_instructions="Instructions",
        )
        assert "# Tools" not in result
        assert "## Skills" not in result
        assert "Instructions" in result

    def test_assemble_skips_empty_lists(self) -> None:
        """Test empty lists are skipped."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(
            library=library,
            tools=[],
            skills=[],
            mcps=[],
        )
        assert "# Tools" not in result
        assert "## Skills" not in result
        assert "## MCP Servers" not in result

    def test_assemble_sections_separated_by_double_newline(self) -> None:
        """Test sections are separated by double newline."""
        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(
            library=library,
            tools=[MockTool()],
        )
        # Should have double newline between base and tools
        assert "\n\n# Tools" in result

    def test_assemble_tool_without_instruction_file_skipped(self) -> None:
        """Test tools without an instruction .md file are silently skipped."""

        class UnknownTool(BaseAgentTool[MockParams]):
            name = "unknown_tool"
            description = "No .md file"
            args_schema = MockParams

            async def execute(self, params: MockParams) -> ToolResult:
                return ToolResult(output="mock")

        library = PromptLibrary()
        assembler = SystemPromptAssembler()
        result = assembler.assemble(
            library=library,
            tools=[MockTool(), UnknownTool()],
        )
        assert "# Tools" in result
        assert library.get("tools/bash") in result


class TestSubclassOverride:
    """Tests for subclass RECIPE override."""

    def test_subclass_can_reorder(self) -> None:
        """Test subclass can change RECIPE order."""

        class CustomAssembler(SystemPromptAssembler):
            RECIPE = [
                FragmentRef("system/base"),
                FragmentRef("system/user_instructions", condition=_has_user_instructions),
                FragmentRef("system/tools", condition=_has_tools),
            ]

        library = PromptLibrary()
        assembler = CustomAssembler()
        result = assembler.assemble(
            library=library,
            tools=[MockTool()],
            user_instructions="USER",
        )
        user_pos = result.index("USER")
        tools_pos = result.index("# Tools")

        assert user_pos < tools_pos
