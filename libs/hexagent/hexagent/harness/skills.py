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

        Satisfies the :class:`~hexagent.types.SkillCatalog` protocol.

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

        logger.info("Starting skill discovery in %d paths: %s", len(self._search_paths), self._search_paths)

        for base_path in self._search_paths:
            # Single batched command using 'find':
            # 1. -maxdepth 2 -mindepth 2: Look exactly in search_path/*/file.md
            # 2. \( -name ... -o -name ... \): Match either SKILL.md or skill.md
            # 3. -printf: Print delimiter and the directory (%h)
            # 4. -exec cat: Print the file content
            # 
            # This avoids shell glob issues and nested shell escaping bugs ($1).
            qbase = shlex.quote(base_path)
            name_filters = " -o ".join(f'-name "{name}"' for name in _SKILL_FILENAMES)
            cmd = (
                f"find {qbase} -maxdepth 2 -mindepth 2 "
                f"\\( {name_filters} \\) "
                f'-printf "{_SKILL_DELIMITER}:%h\\n" -exec cat {{}} \\; -printf "\\n"'
            )
            
            logger.debug("Scanning path %s with command: %s", base_path, cmd)
            result = await self._computer.run(cmd)
            
            # find returns 0 even if no files match. We only care about output.
            if result.exit_code != 0:
                logger.warning("Skill discovery command failed in %s (exit %d): %s", base_path, result.exit_code, result.stderr)
                continue

            if not result.stdout.strip():
                logger.info("No skill files found in %s", base_path)
                continue

            logger.debug("Raw discovery output from %s:\n%s", base_path, result.stdout)

            # Parse batched output into individual skill chunks.
            # A directory may appear twice (SKILL.md + skill.md); first wins.
            seen_dirs: set[str] = set()
            chunks = self._parse_batch_output(result.stdout)
            logger.info("Found %d potential skill chunks in %s", len(chunks), base_path)

            for skill_dir, raw_content in chunks:
                if skill_dir in seen_dirs:
                    logger.debug("Skipping duplicate directory: %s", skill_dir)
                    continue
                seen_dirs.add(skill_dir)

                try:
                    spec = parse_skill_md(raw_content)
                    # Spec requires name to match the directory name
                    dir_basename = skill_dir.rsplit("/", 1)[-1]
                    validate_skill_dir_name(spec.frontmatter.name, dir_basename)
                except SkillError as e:
                    logger.warning("Skipping %s: invalid SKILL.md or directory mismatch. Error: %s", skill_dir, str(e))
                    continue

                fm = spec.frontmatter
                skill = Skill(name=fm.name, description=fm.description, path=skill_dir)
                logger.info("Discovered skill: %s (at %s)", fm.name, skill_dir)
                self._skills[fm.name] = skill
                discovered.append(skill)

        logger.info("Discovery complete. Total skills found: %d", len(discovered))
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
