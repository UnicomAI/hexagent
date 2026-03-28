"""Tests for harness/skills.py -- SkillResolver discovery and loading."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest

from clawwork.harness.skills import SkillResolver
from clawwork.types import CLIResult

# ---------------------------------------------------------------------------
# Mock Computer
# ---------------------------------------------------------------------------

_VALID_SKILL_MD = """\
---
name: pdf
description: Extract text from PDFs
---
# PDF Skill

Use this to extract text from PDF files.
"""

_INVALID_NAME_SKILL_MD = """\
---
name: PDF_Bad
description: Invalid name format
---
Body text.
"""

_MISSING_NAME_SKILL_MD = """\
---
description: No name here
---
Body text.
"""


class MockComputer:
    """Fake Computer that returns preconfigured CLI results."""

    def __init__(self, responses: dict[str, CLIResult] | None = None) -> None:
        self._responses = responses or {}
        self.is_running = True

    async def start(self) -> None:
        pass

    async def run(self, command: str, *, timeout: float | None = None) -> CLIResult:
        for key, result in self._responses.items():
            if key in command:
                return result
        return CLIResult(stdout="", stderr="", exit_code=1)

    async def upload(self, src: str, dst: str) -> None:
        pass

    async def download(self, src: str, dst: str) -> None:
        pass

    async def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# SkillResolver._parse_batch_output
# ---------------------------------------------------------------------------


class TestParseBatchOutput:
    def test_parses_single_skill(self) -> None:
        output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        results = SkillResolver._parse_batch_output(output)
        assert len(results) == 1
        assert results[0][0] == "/mnt/skills/pdf"
        assert "---" in results[0][1]

    def test_parses_multiple_skills(self) -> None:
        output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n===SKILL_FILE===:/mnt/skills/commit\n{_VALID_SKILL_MD}\n"
        results = SkillResolver._parse_batch_output(output)
        assert len(results) == 2

    def test_empty_output_returns_empty(self) -> None:
        assert SkillResolver._parse_batch_output("") == []

    def test_skips_chunks_without_content(self) -> None:
        output = "===SKILL_FILE===:/mnt/skills/empty\n"
        results = SkillResolver._parse_batch_output(output)
        assert results == []


# ---------------------------------------------------------------------------
# SkillResolver.discover / has / load_content
# ---------------------------------------------------------------------------


class TestSkillResolverDiscover:
    def _make_resolver(self, batch_output: str) -> SkillResolver:
        responses = {"for f in": CLIResult(stdout=batch_output, exit_code=0)}
        return SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))

    async def test_discover_valid_skill(self) -> None:
        output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        resolver = self._make_resolver(output)
        skills = await resolver.discover()
        assert len(skills) == 1
        assert skills[0].name == "pdf"
        assert skills[0].description == "Extract text from PDFs"
        assert skills[0].path == "/mnt/skills/pdf"

    async def test_discover_skips_missing_name(self) -> None:
        output = f"===SKILL_FILE===:/mnt/skills/bad\n{_MISSING_NAME_SKILL_MD}\n"
        resolver = self._make_resolver(output)
        skills = await resolver.discover()
        assert len(skills) == 0

    async def test_discover_skips_invalid_name(self) -> None:
        output = f"===SKILL_FILE===:/mnt/skills/bad\n{_INVALID_NAME_SKILL_MD}\n"
        resolver = self._make_resolver(output)
        skills = await resolver.discover()
        assert len(skills) == 0

    async def test_discover_empty_search_paths(self) -> None:
        resolver = SkillResolver(MockComputer(), search_paths=())
        skills = await resolver.discover()
        assert skills == []

    async def test_discover_handles_command_failure(self) -> None:
        resolver = SkillResolver(MockComputer(), search_paths=("/mnt/skills",))
        skills = await resolver.discover()
        assert skills == []

    async def test_discover_skips_name_dir_mismatch(self) -> None:
        """Skill name in SKILL.md must match the directory name."""
        output = f"===SKILL_FILE===:/mnt/skills/wrong-dir\n{_VALID_SKILL_MD}\n"
        resolver = self._make_resolver(output)
        skills = await resolver.discover()
        assert len(skills) == 0

    async def test_discover_deduplicates_same_directory(self) -> None:
        """If both SKILL.md and skill.md exist, only the first match wins."""
        output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        resolver = self._make_resolver(output)
        skills = await resolver.discover()
        assert len(skills) == 1


class TestSkillResolverHas:
    async def test_has_returns_true_after_discover(self) -> None:
        output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        responses = {"for f in": CLIResult(stdout=output, exit_code=0)}
        resolver = SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))
        await resolver.discover()
        assert await resolver.has("pdf") is True

    async def test_has_returns_false_for_unknown_skill(self) -> None:
        resolver = SkillResolver(MockComputer(), search_paths=())
        assert await resolver.has("nonexistent") is False


class TestSkillResolverLoadContent:
    async def test_load_content_returns_body_with_path_prefix(self) -> None:
        batch_output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        responses = {
            "for f in": CLIResult(stdout=batch_output, exit_code=0),
            "cat": CLIResult(stdout=_VALID_SKILL_MD, exit_code=0),
        }
        resolver = SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))
        await resolver.discover()
        content = await resolver.load_content("pdf")
        assert content.startswith("Base directory for this skill: /mnt/skills/pdf")
        assert "# PDF Skill" in content

    async def test_load_content_reads_fresh_each_time(self) -> None:
        batch_output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        responses = {
            "for f in": CLIResult(stdout=batch_output, exit_code=0),
            "cat": CLIResult(stdout=_VALID_SKILL_MD, exit_code=0),
        }
        resolver = SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))
        await resolver.discover()
        first = await resolver.load_content("pdf")
        second = await resolver.load_content("pdf")
        assert first == second
        assert first is not second  # not cached, fresh read each time

    async def test_load_content_raises_for_unknown_skill(self) -> None:
        resolver = SkillResolver(MockComputer(), search_paths=())
        with pytest.raises(KeyError, match="Skill not discovered"):
            await resolver.load_content("nonexistent")

    async def test_load_content_falls_back_to_lowercase(self) -> None:
        """If SKILL.md fails, load_content tries skill.md."""
        batch_output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        responses = {
            "for f in": CLIResult(stdout=batch_output, exit_code=0),
            # SKILL.md fails, skill.md succeeds
            "SKILL.md": CLIResult(stdout="", stderr="not found", exit_code=1),
            "skill.md": CLIResult(stdout=_VALID_SKILL_MD, exit_code=0),
        }
        resolver = SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))
        await resolver.discover()
        content = await resolver.load_content("pdf")
        assert "# PDF Skill" in content

    async def test_load_content_raises_on_read_failure(self) -> None:
        batch_output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        responses = {
            "for f in": CLIResult(stdout=batch_output, exit_code=0),
            # no cat response -> all filenames fail
        }
        resolver = SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))
        await resolver.discover()
        with pytest.raises(RuntimeError, match="Failed to read"):
            await resolver.load_content("pdf")
