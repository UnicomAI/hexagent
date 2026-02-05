"""Prompt template library backed by .md fragment files.

Loads fragment files from the ``prompts/`` package directory via
``importlib.resources`` for wheel compatibility.  Keys are derived from
relative paths with the ``.md`` extension stripped:
``system/base.md`` -> ``"system/base"``.

Fragment files use ``str.format_map()`` for variable substitution.
Literal braces in fragment text must be escaped as ``{{`` / ``}}``.
"""

from __future__ import annotations

import importlib.resources
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from importlib.abc import Traversable


class PromptLibrary:
    """Registry of prompt template fragments.

    Scans the ``prompts/`` package tree on construction and exposes
    templates by key.  Additional templates can be registered
    programmatically (e.g. for custom tools).

    Examples:
        ```python
        library = PromptLibrary()

        # Raw template
        template = library.get("system/base")

        # Render with variables
        rendered = library.render("system/base", {"agent_name": "MyAgent"})

        # Programmatic registration
        library.register("tools/my_custom", "Description of {tool_name}.")
        ```
    """

    def __init__(self) -> None:
        """Initialize the library by scanning fragment files."""
        self._templates: dict[str, str] = {}
        self._scan()

    # --- Public API ---

    def get(self, key: str) -> str:
        """Get a raw template by key.

        Args:
            key: Template key (e.g. ``"system/base"``).

        Returns:
            The raw template string.

        Raises:
            KeyError: If no template with the given key exists.
        """
        if key not in self._templates:
            msg = f"Prompt template not found: {key}"
            raise KeyError(msg)
        return self._templates[key]

    def render(self, key: str, template_vars: dict[str, Any]) -> str:
        """Render a template with variable substitution.

        Uses ``str.format_map()`` — all ``{variable}`` placeholders in
        the template must be present in *template_vars* or a ``KeyError``
        is raised.  Literal braces must be escaped as ``{{`` / ``}}``.

        Args:
            key: Template key.
            template_vars: Variable bindings for substitution.

        Returns:
            The rendered template string.

        Raises:
            KeyError: If the key is missing or a template variable
                is not present in *template_vars*.
        """
        template = self.get(key)
        return template.format_map(template_vars)

    def register(self, key: str, template: str) -> None:
        """Register a template programmatically.

        Overwrites any existing template with the same key.

        Args:
            key: Template key.
            template: The template string.
        """
        self._templates[key] = template

    def has(self, key: str) -> bool:
        """Check if a template key exists.

        Args:
            key: Template key.

        Returns:
            True if the key exists.
        """
        return key in self._templates

    def keys(self) -> list[str]:
        """Return all registered template keys, sorted.

        Returns:
            Sorted list of template keys.
        """
        return sorted(self._templates)

    # --- Private ---

    def _scan(self) -> None:
        """Scan the prompts package for .md fragment files."""
        package = importlib.resources.files("openagent.prompts")
        self._scan_dir(package, "")

    def _scan_dir(self, directory: Traversable, prefix: str) -> None:
        """Recursively scan a directory for .md files.

        Args:
            directory: An importlib.resources Traversable directory.
            prefix: Current path prefix for key construction.
        """
        for item in directory.iterdir():
            name: str = item.name
            if item.is_dir() and not name.startswith("_"):
                child_prefix = f"{prefix}{name}/" if prefix else f"{name}/"
                self._scan_dir(item, child_prefix)
            elif item.is_file() and name.endswith(".md"):
                key = f"{prefix}{name[:-3]}"
                self._templates[key] = item.read_text(encoding="utf-8")
