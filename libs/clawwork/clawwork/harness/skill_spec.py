"""SKILL.md parsing and validation per the Agent Skills specification.

Provides :func:`parse_skill_md` to turn raw SKILL.md content into a
validated :class:`SkillSpec`, and :func:`validate_skill_name` for
standalone name checks (e.g. matching directory names).

See https://agentskills.io/specification for the community standard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from clawwork.exceptions import SkillParseError, SkillValidationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NAME_MAX_LEN = 64
_DESC_MAX_LEN = 1024
_COMPAT_MAX_LEN = 500

# Matches: lowercase alphanumeric segments separated by single hyphens.
# Naturally rejects leading/trailing hyphens and consecutive hyphens.
_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillFrontmatter:
    """Validated SKILL.md frontmatter fields.

    Represents the structured YAML metadata between ``---`` delimiters.
    All fields satisfy the Agent Skills specification constraints
    at construction time.

    Attributes:
        name: Skill identifier (1-64 chars, lowercase alphanumeric + hyphens).
        description: What the skill does and when to use it (1-1024 chars).
        license: License name or reference, if provided.
        compatibility: Environment requirements, if provided (1-500 chars).
        metadata: Arbitrary string key-value pairs.
    """

    name: str
    description: str
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillSpec:
    """Parsed and validated representation of a SKILL.md file.

    Combines the structured :class:`SkillFrontmatter` with the freeform
    markdown body. These are kept separate because they have different
    schemas (strict vs none), lifecycles (frontmatter at discovery,
    body at activation), and consumers.

    Attributes:
        frontmatter: Validated YAML metadata.
        body: Markdown content after the frontmatter block.
    """

    frontmatter: SkillFrontmatter
    body: str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_skill_name(name: str) -> None:
    """Validate a skill name against the Agent Skills specification.

    Rules:
    - 1-64 characters
    - Lowercase alphanumeric and hyphens only
    - Must not start or end with a hyphen
    - Must not contain consecutive hyphens

    Args:
        name: The skill name to validate.

    Raises:
        SkillValidationError: If the name violates any rule.
    """
    if not name:
        msg = "Skill name must not be empty"
        raise SkillValidationError(msg)

    if len(name) > _NAME_MAX_LEN:
        msg = f"Skill name must be at most {_NAME_MAX_LEN} characters, got {len(name)}"
        raise SkillValidationError(msg)

    if not _NAME_RE.fullmatch(name):
        msg = (
            f"Skill name {name!r} is invalid: must contain only lowercase "
            "alphanumeric characters and hyphens, must not start or end "
            "with a hyphen, and must not contain consecutive hyphens"
        )
        raise SkillValidationError(msg)


def validate_skill_dir_name(skill_name: str, dir_name: str) -> None:
    """Validate that a skill's directory name matches its declared name.

    The Agent Skills specification requires that the ``name`` field in
    SKILL.md matches the parent directory name.

    Args:
        skill_name: The ``name`` from SKILL.md frontmatter.
        dir_name: The actual directory name on disk.

    Raises:
        SkillValidationError: If the names do not match.
    """
    if skill_name != dir_name:
        msg = f"Skill name {skill_name!r} does not match directory name {dir_name!r}: the spec requires these to be identical"
        raise SkillValidationError(msg)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _extract_frontmatter(raw: str) -> tuple[str, str]:
    """Split raw SKILL.md into (yaml_block, body).

    Raises:
        SkillParseError: If delimiters are missing or malformed.
    """
    lines = raw.strip().splitlines(keepends=True)

    if not lines or lines[0].strip() != "---":
        msg = "SKILL.md must start with '---' frontmatter delimiter"
        raise SkillParseError(msg)

    # Find the closing --- line (first line after the opener that is exactly ---)
    close_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close_idx = i
            break

    if close_idx is None:
        msg = "SKILL.md missing closing '---' frontmatter delimiter"
        raise SkillParseError(msg)

    yaml_block = "".join(lines[1:close_idx])
    body = "".join(lines[close_idx + 1 :]).strip()

    return yaml_block, body


def _validate_description(description: str) -> None:
    """Validate the description field.

    Raises:
        SkillValidationError: If the description is empty or too long.
    """
    if not description:
        msg = "Skill description must not be empty"
        raise SkillValidationError(msg)

    if len(description) > _DESC_MAX_LEN:
        msg = f"Skill description must be at most {_DESC_MAX_LEN} characters, got {len(description)}"
        raise SkillValidationError(msg)


def _validate_compatibility(compatibility: str) -> None:
    """Validate the optional compatibility field.

    Raises:
        SkillValidationError: If the compatibility string is too long.
    """
    if len(compatibility) > _COMPAT_MAX_LEN:
        msg = f"Skill compatibility must be at most {_COMPAT_MAX_LEN} characters, got {len(compatibility)}"
        raise SkillValidationError(msg)


def _validate_metadata(metadata: object) -> dict[str, str]:
    """Validate and normalise the optional metadata mapping.

    Args:
        metadata: Raw value from YAML (expected ``dict[str, str]``).

    Returns:
        A validated ``dict[str, str]``.

    Raises:
        SkillValidationError: If metadata is not a string-to-string mapping.
    """
    if not isinstance(metadata, dict):
        msg = f"Skill metadata must be a mapping, got {type(metadata).__name__}"
        raise SkillValidationError(msg)

    for key, value in metadata.items():
        if not isinstance(key, str):
            msg = f"Skill metadata key must be a string, got {type(key).__name__}: {key!r}"
            raise SkillValidationError(msg)
        if not isinstance(value, str):
            msg = f"Skill metadata value for {key!r} must be a string, got {type(value).__name__}: {value!r}"
            raise SkillValidationError(msg)

    return dict(metadata)


def _parse_frontmatter_yaml(yaml_block: str) -> SkillFrontmatter:
    """Parse and validate a YAML frontmatter block into a :class:`SkillFrontmatter`.

    Args:
        yaml_block: Raw YAML string between ``---`` delimiters.

    Returns:
        A validated SkillFrontmatter.

    Raises:
        SkillParseError: If the YAML is invalid or required fields are missing.
        SkillValidationError: If field values violate spec constraints.
    """
    try:
        raw = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        msg = f"Invalid YAML in frontmatter: {exc}"
        raise SkillParseError(msg) from exc

    if raw is None:
        msg = "SKILL.md frontmatter is empty"
        raise SkillParseError(msg)

    if not isinstance(raw, dict):
        msg = f"Frontmatter must be a YAML mapping, got {type(raw).__name__}"
        raise SkillParseError(msg)

    # --- Required fields ---

    name = raw.get("name")
    if name is None:
        msg = "SKILL.md missing required field: 'name'"
        raise SkillParseError(msg)
    name = str(name)
    validate_skill_name(name)

    description = raw.get("description")
    if description is None:
        msg = "SKILL.md missing required field: 'description'"
        raise SkillParseError(msg)
    description = str(description)
    _validate_description(description)

    # --- Optional fields ---

    skill_license: str | None = None
    if "license" in raw:
        skill_license = str(raw["license"])

    compatibility: str | None = None
    if "compatibility" in raw:
        compatibility = str(raw["compatibility"])
        _validate_compatibility(compatibility)

    metadata: dict[str, str] = {}
    if "metadata" in raw:
        metadata = _validate_metadata(raw["metadata"])

    return SkillFrontmatter(
        name=name,
        description=description,
        license=skill_license,
        compatibility=compatibility,
        metadata=metadata,
    )


def parse_skill_md(raw: str) -> SkillSpec:
    """Parse and validate a SKILL.md file into a :class:`SkillSpec`.

    Uses ``yaml.safe_load`` for frontmatter parsing to correctly handle
    multiline values, quoted strings, and other YAML features.

    Args:
        raw: The full SKILL.md file content.

    Returns:
        A validated SkillSpec.

    Raises:
        SkillParseError: If the file structure or YAML is invalid,
            or if required fields are missing.
        SkillValidationError: If field values violate spec constraints.

    Examples:
        ```python
        spec = parse_skill_md('''---
        name: pdf-processing
        description: Extract text from PDFs.
        ---
        # Instructions
        Use this skill to process PDF files.
        ''')
        assert spec.frontmatter.name == "pdf-processing"
        ```
    """
    yaml_block, body = _extract_frontmatter(raw)
    frontmatter = _parse_frontmatter_yaml(yaml_block)
    return SkillSpec(frontmatter=frontmatter, body=body)
