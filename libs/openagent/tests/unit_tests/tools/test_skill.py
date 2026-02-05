"""Tests for SkillTool."""

from __future__ import annotations

from openagent.tools import SkillTool


class TestSkillTool:
    """Tests for SkillTool."""

    def test_name(self) -> None:
        """SkillTool name is 'skill'."""
        tool = SkillTool()
        assert tool.name == "skill"

    def test_description(self) -> None:
        """SkillTool has a description."""
        tool = SkillTool()
        assert tool.description != ""

    async def test_execute_registered_skill(self) -> None:
        """Execute with registered skill name."""
        tool = SkillTool(registered_skills={"commit"})
        result = await tool(skill="commit")
        assert result.output == "Launching skill: commit"
        assert result.error is None

    async def test_execute_with_args(self) -> None:
        """Execute with skill name and args."""
        tool = SkillTool(registered_skills={"canvas-design"})
        result = await tool(skill="canvas-design", args="brand headline")
        assert result.output == "Launching skill: canvas-design"
        assert result.error is None

    async def test_execute_various_skill_names(self) -> None:
        """Execute works with various registered skill names."""
        skill_names = {"commit", "review-pr", "pdf", "canvas-design"}
        tool = SkillTool(registered_skills=skill_names)
        for skill_name in skill_names:
            result = await tool(skill=skill_name)
            assert result.output == f"Launching skill: {skill_name}"


class TestSkillToolUnknownSkill:
    """Tests for SkillTool error handling with unknown skills."""

    async def test_unknown_skill_returns_error(self) -> None:
        """Unknown skill returns error result."""
        tool = SkillTool(registered_skills={"commit", "review-pr"})
        result = await tool(skill="non-existent-skill")
        assert result.error == "Unknown skill: non-existent-skill"
        assert result.output is None

    async def test_no_registered_skills_rejects_all(self) -> None:
        """When registered_skills is None, all skills are rejected."""
        tool = SkillTool(registered_skills=None)
        result = await tool(skill="any-skill-name")
        assert result.error == "Unknown skill: any-skill-name"
        assert result.output is None

    async def test_empty_registered_skills_rejects_all(self) -> None:
        """Empty registered_skills set rejects all skills."""
        tool = SkillTool(registered_skills=set())
        result = await tool(skill="commit")
        assert result.error == "Unknown skill: commit"
        assert result.output is None

    async def test_default_constructor_rejects_all(self) -> None:
        """Default constructor with no args rejects all skills."""
        tool = SkillTool()
        result = await tool(skill="commit")
        assert result.error == "Unknown skill: commit"
        assert result.output is None
