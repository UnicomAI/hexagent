"""Prompt content loading.

Read-only loader for .md fragment files from the ``prompts/fragments/``
sub-package via ``importlib.resources`` for wheel compatibility.  Keys
are derived from filenames: ``system_prompt_identity.md`` →
``"system_prompt_identity"``.

This module has no mutable state.  All results are cached for the
lifetime of the process (content files don't change during a session).
"""

from __future__ import annotations

import functools
import importlib.resources
import re

_PLACEHOLDER_RE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")


@functools.cache
def _scan_package_keys() -> frozenset[str]:
    """Discover all .md fragment keys in the package."""
    package = importlib.resources.files("clawwork.prompts.fragments")
    keys: set[str] = set()
    for item in package.iterdir():
        if item.is_file() and item.name.endswith(".md"):
            keys.add(item.name[:-3])
    return frozenset(keys)


@functools.cache
def load(key: str) -> str:
    """Load a prompt fragment by key.

    Results are cached — repeated calls with the same key return the
    same string without hitting the filesystem.

    Args:
        key: Fragment key (e.g. ``"system_prompt_identity"``).

    Returns:
        The fragment text.

    Raises:
        KeyError: If no fragment with the given key exists.
    """
    package = importlib.resources.files("clawwork.prompts.fragments")
    resource = package.joinpath(f"{key}.md")
    try:
        return resource.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, TypeError) as exc:
        msg = f"Prompt fragment not found: '{key}'"
        raise KeyError(msg) from exc


def find(prefix: str) -> list[str]:
    """Find all fragment keys matching a prefix, sorted.

    Args:
        prefix: Key prefix to match (e.g. ``"tool_instruction_bash_"``).

    Returns:
        Sorted list of matching keys.
    """
    return sorted(k for k in _scan_package_keys() if k.startswith(prefix))


def substitute(template: str, **variables: str) -> str:
    """Replace ``${KEY}`` placeholders with values.

    Unlike ``string.Template``, this does NOT interpret ``$`` as a
    special character.  Only explicit ``${KEY}`` patterns matching
    a provided keyword argument are replaced.  All other ``$``
    characters are left as-is (no escaping needed in .md files).

    Only uppercase placeholders matching ``[A-Z][A-Z0-9_]*`` are
    checked — patterns like ``${lowercase}``, ``${OBJ.field}``, or
    ``${FN()}`` are ignored.

    Args:
        template: Text containing ``${KEY}`` placeholders.
        **variables: Keyword arguments mapping placeholder names to values.

    Returns:
        The template with all provided placeholders resolved.

    Raises:
        ValueError: If any ``${KEY}`` placeholders remain unresolved
            after substitution.
    """
    result = template
    for key, value in variables.items():
        result = result.replace(f"${{{key}}}", value)
    remaining = _PLACEHOLDER_RE.findall(result)
    if remaining:
        unresolved = ", ".join(f"${{{v}}}" for v in remaining)
        msg = f"Unresolved placeholders: {unresolved}"
        raise ValueError(msg)
    return result
