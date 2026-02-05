"""Skill tool for invoking specialized capabilities.

This module provides the SkillTool which allows agents to invoke
specialized skills by name with optional arguments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from openagent.tools.base import BaseAgentTool
from openagent.types import SkillToolParams, ToolResult

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet


class SkillTool(BaseAgentTool[SkillToolParams]):
    """Tool for invoking skills by name.

    Skills provide specialized capabilities and domain knowledge.
    This tool launches a skill and returns a confirmation message,
    or an error if the skill is unknown.

    Args:
        registered_skills: Set of valid skill names. Only registered skills are allowed.

    Examples:
        ```python
        tool = SkillTool(registered_skills={"commit", "review-pr"})

        result = await tool(skill="commit", args="-m 'Fix bug'")
        # result.output == "Launching skill: commit"

        result = await tool(skill="unknown")
        # result.error == "Unknown skill: unknown"
        ```
    """

    name: str = "skill"
    description: str = "Execute a skill by name with optional arguments."
    args_schema = SkillToolParams

    def __init__(self, registered_skills: AbstractSet[str] | None = None) -> None:
        """Initialize the SkillTool.

        Args:
            registered_skills: Set of valid skill names. Only registered skills are allowed.
        """
        self._registered_skills = registered_skills or frozenset()

    async def execute(self, params: SkillToolParams) -> ToolResult:
        """Execute the skill invocation.

        Args:
            params: Validated skill parameters (skill name and optional args).

        Returns:
            ToolResult with confirmation message, or error if skill is unknown.
        """
        if params.skill not in self._registered_skills:
            return ToolResult(error=f"Unknown skill: {params.skill}")
        return ToolResult(output=f"Launching skill: {params.skill}")
