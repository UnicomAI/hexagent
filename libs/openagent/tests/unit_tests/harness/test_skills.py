"""Tests for harness/skills.py — SkillResolver, frontmatter parsing."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest

from openagent.harness.skills import SkillResolver, _parse_frontmatter
from openagent.types import CLIResult

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

_MISSING_NAME_SKILL_MD = """\
---
description: No name here
---
Body text.
"""

_EMPTY_BODY_SKILL_MD = """\
---
name: empty
description: Skill with no body
---
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

    async def stop(self) -> None:
        pass


# ---------------------------------------------------------------------------
# _parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_valid_frontmatter(self) -> None:
        metadata, body = _parse_frontmatter(_VALID_SKILL_MD)
        assert metadata["name"] == "pdf"
        assert metadata["description"] == "Extract text from PDFs"
        assert "# PDF Skill" in body

    def test_missing_opening_delimiter_raises(self) -> None:
        with pytest.raises(ValueError, match="must start with"):
            _parse_frontmatter("no frontmatter here")

    def test_missing_closing_delimiter_raises(self) -> None:
        with pytest.raises(ValueError, match="missing closing"):
            _parse_frontmatter("---\nname: test\nbody without closing")

    def test_empty_frontmatter(self) -> None:
        metadata, body = _parse_frontmatter("---\n---\nBody text.")
        assert metadata == {}
        assert body == "Body text."

    def test_ignores_lines_without_colon(self) -> None:
        raw = "---\nname: test\ninvalid line\n---\nBody."
        metadata, _ = _parse_frontmatter(raw)
        assert metadata == {"name": "test"}

    def test_preserves_value_with_colons(self) -> None:
        raw = "---\nurl: https://example.com:8080\n---\nBody."
        metadata, _ = _parse_frontmatter(raw)
        assert metadata["url"] == "https://example.com:8080"


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

    async def test_discover_skips_empty_body(self) -> None:
        output = f"===SKILL_FILE===:/mnt/skills/empty\n{_EMPTY_BODY_SKILL_MD}\n"
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

    async def test_load_content_raises_on_empty_body(self) -> None:
        batch_output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        responses = {
            "for f in": CLIResult(stdout=batch_output, exit_code=0),
            "cat": CLIResult(stdout=_EMPTY_BODY_SKILL_MD, exit_code=0),
        }
        resolver = SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))
        await resolver.discover()
        with pytest.raises(RuntimeError, match="has no content body"):
            await resolver.load_content("pdf")

    async def test_load_content_raises_on_read_failure(self) -> None:
        batch_output = f"===SKILL_FILE===:/mnt/skills/pdf\n{_VALID_SKILL_MD}\n"
        responses = {
            "for f in": CLIResult(stdout=batch_output, exit_code=0),
            # cat command will fail (no matching response → exit_code=1)
        }
        resolver = SkillResolver(MockComputer(responses), search_paths=("/mnt/skills",))
        await resolver.discover()
        with pytest.raises(RuntimeError, match="Failed to read"):
            await resolver.load_content("pdf")
