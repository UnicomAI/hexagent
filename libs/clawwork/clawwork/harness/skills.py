"""Skill discovery and content loading.

SkillResolver scans configured directories on a Computer for skill
folders, parses SKILL.md frontmatter for metadata, and loads
skill content on demand (always fresh from disk).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from clawwork.exceptions import SkillError
from clawwork.harness.skill_spec import parse_skill_md, validate_skill_dir_name
from clawwork.types import Skill

if TYPE_CHECKING:
    from clawwork.computer.base import Computer

logger = logging.getLogger(__name__)

DEFAULT_SKILL_PATHS: tuple[str, ...] = (
    "/mnt/skills",
    "~/.clawwork/skills",
    ".clawwork/skills",
)

_SKILL_FILENAMES = ("SKILL.md", "skill.md")
_SKILL_DELIMITER = "===SKILL_FILE==="


class SkillResolver:
    r"""Discovers skills from the filesystem and lazily loads their content.

    Uses the Computer protocol to run filesystem commands, making it
    work with both LocalNativeComputer and RemoteE2BComputer.

    Discovery uses a single batched shell command per search path to
    avoid N+1 round-trip overhead with remote computers.

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

    @property
    def search_paths(self) -> tuple[str, ...]:
        """The configured search paths."""
        return self._search_paths

    async def has(self, name: str) -> bool:
        """Return True if *name* is a known skill, re-discovering on cache miss.

        Satisfies the :class:`~clawwork.types.SkillCatalog` protocol.

        Args:
            name: The skill name to check.

        Returns:
            True if the skill exists (possibly after re-discovery).
        """
        if name in self._skills:
            return True
        await self.discover()
        return name in self._skills

    async def discover(self) -> list[Skill]:
        """Scan search paths for skill directories and parse metadata.

        Each subdirectory containing a SKILL.md file is treated as a skill.
        The SKILL.md frontmatter is validated against the Agent Skills spec.

        Uses a single shell command per search path to batch discovery,
        avoiding N+1 round-trip overhead with remote computers.

        Returns:
            List of discovered Skill objects.
        """
        self._skills.clear()
        discovered: list[Skill] = []

        for base_path in self._search_paths:
            # Single batched command: find SKILL.md or skill.md files,
            # print delimiter + directory path + file content for each.
            # Uses shell glob (no `find` dependency) and quoting.
            # Iterates both casing variants; only the first match per
            # directory wins because duplicates are filtered downstream.
            globs = " ".join(f'"{base_path}"/*/{name}' for name in _SKILL_FILENAMES)
            cmd = f'for f in {globs}; do [ -f "$f" ] && printf "{_SKILL_DELIMITER}:%s\\n" "$(dirname "$f")" && cat "$f" && printf "\\n"; done'
            result = await self._computer.run(cmd)
            if result.exit_code != 0 or not result.stdout.strip():
                continue

            # Parse batched output into individual skill chunks.
            # A directory may appear twice (SKILL.md + skill.md); first wins.
            seen_dirs: set[str] = set()
            for skill_dir, raw_content in self._parse_batch_output(result.stdout):
                if skill_dir in seen_dirs:
                    continue
                seen_dirs.add(skill_dir)

                try:
                    spec = parse_skill_md(raw_content)
                    # Spec requires name to match the directory name
                    dir_basename = skill_dir.rsplit("/", 1)[-1]
                    validate_skill_dir_name(spec.frontmatter.name, dir_basename)
                except SkillError:
                    logger.warning("Skipping %s: invalid SKILL.md", skill_dir)
                    continue

                fm = spec.frontmatter
                skill = Skill(name=fm.name, description=fm.description, path=skill_dir)
                self._skills[fm.name] = skill
                discovered.append(skill)

        return discovered

    async def load_content(self, name: str) -> str:
        r"""Load the skill's markdown body (always fresh from disk).

        Returns the content wrapped with the skill's base directory:
        ``Base directory for this skill: {path}\n\n{body}``

        Args:
            name: The skill name (must have been discovered first).

        Returns:
            The formatted skill content ready for injection as a user message.

        Raises:
            KeyError: If the skill name was not discovered.
            RuntimeError: If the SKILL.md content cannot be read or parsed.
        """
        if name not in self._skills:
            msg = f"Skill not discovered: {name}"
            raise KeyError(msg)

        skill = self._skills[name]

        # Try each accepted filename casing
        result = None
        for filename in _SKILL_FILENAMES:
            skill_file = f"{skill.path}/{filename}"
            result = await self._computer.run(f'cat "{skill_file}"')
            if result.exit_code == 0:
                break

        if result is None or result.exit_code != 0:
            msg = f"Failed to read SKILL.md in {skill.path}: {result.stderr if result else 'no file found'}"
            raise RuntimeError(msg)

        try:
            spec = parse_skill_md(result.stdout)
        except SkillError as exc:
            msg = f"Failed to parse {skill_file}: {exc}"
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
