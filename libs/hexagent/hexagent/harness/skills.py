"""Skill discovery and content loading.

SkillResolver scans configured directories on a Computer for skill
folders, parses SKILL.md frontmatter for metadata, and loads
skill content on demand (always fresh from disk).
"""

from __future__ import annotations

import logging
import shlex
from typing import TYPE_CHECKING

from hexagent.exceptions import SkillError
from hexagent.harness.skill_spec import parse_skill_md, validate_skill_dir_name
from hexagent.types import Skill

if TYPE_CHECKING:
    from hexagent.computer.base import Computer

logger = logging.getLogger(__name__)

DEFAULT_SKILL_PATHS: tuple[str, ...] = (
    "/mnt/skills",
    "~/.hexagent/skills",
    ".hexagent/skills",
)

_SKILL_FILENAMES = ("SKILL.md", "skill.md")
_SKILL_DELIMITER = "===SKILL_FILE==="


class SkillResolver:
    r"""Discovers skills from the filesystem and maintains a memory registry.

    Uses the Computer protocol to run filesystem commands. Once discovered,
    skills are cached in memory to avoid redundant disk scans.

    Supports dynamic updates (add/delete/toggle) without full re-discovery.

    Examples:
        ```python
        resolver = SkillResolver(computer, search_paths=("/mnt/skills",))
        skills = await resolver.discover()
        # skills == [Skill(name="pdf", description="...", path="/mnt/skills/pdf")]

        content = await resolver.load_content("pdf")
        # content == "Base directory for this skill: /mnt/skills/pdf\n\n..."
        ```
    """

    def __init__(
        self,
        computer: Computer,
        search_paths: tuple[str, ...] | list[str],
    ) -> None:
        """Initialize the resolver.

        Args:
            computer: The Computer instance for filesystem access.
            search_paths: Directories to scan for skill folders.
        """
        self._computer = computer
        self._search_paths = tuple(search_paths)
        self._skills: dict[str, Skill] = {}
        self._initialized = False

    @property
    def search_paths(self) -> tuple[str, ...]:
        """The configured search paths."""
        return self._search_paths

    async def has(self, name: str) -> bool:
        """Return True if *name* is a known skill.

        Satisfies the :class:`~hexagent.types.SkillCatalog` protocol.
        """
        if not self._initialized:
            await self.discover()
        return name in self._skills

    async def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        if not self._initialized:
            await self.discover()
        return self._skills.get(name)

    async def set_enabled(self, name: str, enabled: bool) -> None:
        """Enable or disable a skill in memory without scanning disk."""
        if name in self._skills:
            old_skill = self._skills[name]
            from hexagent.types import Skill
            self._skills[name] = Skill(
                name=old_skill.name,
                description=old_skill.description,
                path=old_skill.path,
                enabled=enabled
            )
            logger.info("[SkillResolver] Skill %s status updated: enabled=%s", name, enabled)

    async def add_skill_by_path(self, skill_path: str) -> Skill | None:
        """Discover and add a single skill from a specific path.

        Avoids full scan of all search paths.
        """
        logger.info("[SkillResolver] Adding single skill from path: %s", skill_path)
        # Try each accepted filename casing
        raw_content = None
        for filename in _SKILL_FILENAMES:
            skill_file = f"{skill_path}/{filename}"
            result = await self._computer.run(f'cat "{skill_file}"')
            if result.exit_code == 0:
                raw_content = result.stdout
                break

        if not raw_content:
            logger.warning("[SkillResolver] No SKILL.md found in %s", skill_path)
            return None

        try:
            spec = parse_skill_md(raw_content)
            dir_basename = skill_path.rstrip("/").rsplit("/", 1)[-1]
            validate_skill_dir_name(spec.frontmatter.name, dir_basename)
        except SkillError as exc:
            logger.warning("[SkillResolver] Failed to parse skill in %s: %s", skill_path, exc)
            return None

        from hexagent.types import Skill
        fm = spec.frontmatter
        skill = Skill(name=fm.name, description=fm.description, path=skill_path, enabled=True)
        self._skills[fm.name] = skill
        logger.info("[SkillResolver] Added skill to registry: name=%s", fm.name)
        return skill

    async def remove_skill(self, name: str) -> None:
        """Remove a skill from the memory registry."""
        if name in self._skills:
            del self._skills[name]
            logger.info("[SkillResolver] Removed skill from registry: %s", name)

    async def discover(self, force: bool = False, disabled_names: set[str] | None = None) -> list[Skill]:
        """Scan search paths for skill directories (one-time or forced).

        Args:
            force: Whether to re-scan disk even if already initialized.
            disabled_names: Optional set of skill names that should be initialized as disabled.
        """
        if self._initialized and not force:
            logger.debug("[SkillResolver] Discovery skipped (already initialized)")
            return list(self._skills.values())

        logger.info("[SkillResolver] Starting full skill discovery, search_paths=%s", self._search_paths)
        self._skills.clear()
        discovered: list[Skill] = []

        for base_path in self._search_paths:
            qbase = shlex.quote(base_path)
            name_filters = " -o ".join(f'-name "{name}"' for name in _SKILL_FILENAMES)
            cmd = (
                f"find {qbase} -maxdepth 2 -mindepth 2 "
                f"\\( {name_filters} \\) "
                f'-printf "{_SKILL_DELIMITER}:%h\\n" -exec cat {{}} \\; -printf "\\n"'
            )

            result = await self._computer.run(cmd)
            if result.exit_code != 0 or not result.stdout.strip():
                continue

            from hexagent.types import Skill
            chunks = self._parse_batch_output(result.stdout)
            seen_dirs: set[str] = set()

            for skill_dir, raw_content in chunks:
                if skill_dir in seen_dirs:
                    continue
                seen_dirs.add(skill_dir)

                try:
                    spec = parse_skill_md(raw_content)
                    dir_basename = skill_dir.rsplit("/", 1)[-1]
                    validate_skill_dir_name(spec.frontmatter.name, dir_basename)
                except SkillError:
                    continue

                fm = spec.frontmatter
                is_enabled = disabled_names is None or fm.name not in disabled_names
                skill = Skill(name=fm.name, description=fm.description, path=skill_dir, enabled=is_enabled)
                self._skills[fm.name] = skill
                discovered.append(skill)

        self._initialized = True
        logger.info("[SkillResolver] Skill discovery complete, total_skills=%d", len(discovered))
        return discovered

    async def load_content(self, name: str) -> str:
        r"""Load the skill's markdown body (always fresh from disk)."""
        if name not in self._skills:
            msg = f"Skill not discovered: {name}"
            raise KeyError(msg)

        skill = self._skills[name]
        if not skill.enabled:
            logger.debug("[SkillResolver] Skipping load_content for disabled skill: %s", name)
            return ""

        # Try each accepted filename casing
        result = None
        for filename in _SKILL_FILENAMES:
            skill_file = f"{skill.path}/{filename}"
            result = await self._computer.run(f'cat "{skill_file}"')
            if result.exit_code == 0:
                break

        if result is None or result.exit_code != 0:
            msg = f"Failed to read SKILL.md in {skill.path}"
            raise RuntimeError(msg)

        try:
            spec = parse_skill_md(result.stdout)
        except SkillError as exc:
            msg = f"Failed to parse {skill.path}: {exc}"
            raise RuntimeError(msg) from exc

        return f"Base directory for this skill: {skill.path}\n\n{spec.body}"

    @staticmethod
    def _parse_batch_output(output: str) -> list[tuple[str, str]]:
        """Parse batched discovery output into (directory, content) pairs.

        Args:
            output: Raw stdout from the batched discovery command.

        Returns:
            List of (skill_dir, raw_skill_md_content) tuples.
        """
        delimiter_prefix = f"{_SKILL_DELIMITER}:"
        results: list[tuple[str, str]] = []
        chunks = output.split(delimiter_prefix)

        for chunk in chunks[1:]:  # skip everything before first delimiter
            newline_idx = chunk.find("\n")
            if newline_idx == -1:
                continue
            skill_dir = chunk[:newline_idx].strip()
            raw_content = chunk[newline_idx + 1 :].strip()
            if skill_dir and raw_content:
                results.append((skill_dir, raw_content))

        return results
