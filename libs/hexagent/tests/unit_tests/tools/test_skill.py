"""Tests for tools/skill.py — SkillTool."""

from __future__ import annotations

from hexagent.tools.skill import SkillTool
from hexagent.types import SkillToolParams


class _FakeCatalog:
    """Catalog with a fixed set of known skills."""

    def __init__(self, known: set[str]) -> None:
        self._known = known

    async def has(self, name: str) -> bool:
        return name in self._known


class TestSkillTool:
    async def test_execute_known_skill_returns_confirmation(self) -> None:
        tool = SkillTool(catalog=_FakeCatalog({"commit"}))
        result = await tool.execute(SkillToolParams(skill="commit"))
        assert result.output is not None
        assert "commit" in result.output
        assert result.error is None

    async def test_execute_unknown_skill_returns_error(self) -> None:
        tool = SkillTool(catalog=_FakeCatalog(set()))
        result = await tool.execute(SkillToolParams(skill="nonexistent"))
        assert result.error is not None
        assert "nonexistent" in result.error
        assert result.output is None

    async def test_callable_validates_and_executes(self) -> None:
        tool = SkillTool(catalog=_FakeCatalog({"pdf"}))
        result = await tool(skill="pdf")
        assert result.output is not None
        assert "pdf" in result.output
