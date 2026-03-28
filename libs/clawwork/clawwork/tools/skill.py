"""Skill tool for invoking specialized capabilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from clawwork.tools.base import BaseAgentTool
from clawwork.types import SkillToolParams, ToolResult

if TYPE_CHECKING:
    from clawwork.types import SkillCatalog


class SkillTool(BaseAgentTool[SkillToolParams]):
    """Tool for invoking skills by name.

    Delegates validation to a :class:`~clawwork.types.SkillCatalog`,
    which handles caching and mid-session re-discovery internally.
    Actual skill content injection is handled by the middleware.

    Args:
        catalog: Catalog for checking skill availability.
    """

    name: Literal["Skill"] = "Skill"
    description: str = "Execute a skill by name with optional arguments."
    args_schema = SkillToolParams

    def __init__(self, catalog: SkillCatalog) -> None:
        """Initialize with a skill catalog."""
        self._catalog = catalog

    async def execute(self, params: SkillToolParams) -> ToolResult:
        """Validate skill name and return confirmation."""
        if await self._catalog.has(params.skill):
            return ToolResult(output=f"Launching skill: {params.skill}")
        return ToolResult(error=f"Unknown skill: {params.skill}")
