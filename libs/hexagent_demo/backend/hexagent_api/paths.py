"""Centralised path resolution for the HexAgent demo backend.

All runtime directories are derived from a single root — either
``$HEXAGENT_DATA_DIR`` (when set) or ``~/.hexagent``.  Importing
code should call the functions here rather than constructing paths
inline, so that a future rename or restructure only touches this file.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Project name — single constant used to derive default paths.
# Change this if the project is ever renamed.
# ---------------------------------------------------------------------------

_PROJECT_DIR_NAME = "hexagent"

# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------


def data_dir() -> Path:
    """Root data directory.

    Respects ``HEXAGENT_DATA_DIR`` if set, otherwise ``~/.hexagent``.
    """
    env = os.environ.get("HEXAGENT_DATA_DIR")
    if env:
        return Path(env)
    return Path.home() / f".{_PROJECT_DIR_NAME}"


# ---------------------------------------------------------------------------
# Derived directories
# ---------------------------------------------------------------------------


def config_path() -> Path:
    """Path to ``config.json``."""
    return data_dir() / "config.json"


def skills_dir() -> Path:
    """Root directory for user-owned skills (private, inactive)."""
    return data_dir() / "skills"


def bundled_skills_dir() -> Path:
    """Directory containing skills shipped with the application.

    In development this is the ``backend/skills/`` source directory.
    In a PyInstaller bundle it is ``sys._MEIPASS/skills/``.
    """
    import sys  # noqa: PLC0415

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "skills"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent.parent / "skills"


def deps_dir() -> Path:
    """Directory for managed dependencies (e.g. Lima, WSL tools)."""
    return data_dir() / "deps"


def uploads_dir() -> Path:
    """Temporary upload staging directory.

    Uses the system temp dir to avoid filling the data dir with
    large transient files, but keeps a stable project-prefixed name
    so cleanup scripts can find it.
    """
    return Path(tempfile.gettempdir()) / f"{_PROJECT_DIR_NAME}_uploads"


def pdf_cache_dir() -> Path:
    """Cache directory for LibreOffice PDF conversions."""
    return Path(tempfile.gettempdir()) / f"{_PROJECT_DIR_NAME}_pdf_cache"


def vm_dir() -> Path:
    """Root directory for VM assets (``libs/hexagent/sandbox/vm/``).

    In a PyInstaller bundle the sandbox tree is placed at
    ``sys._MEIPASS/sandbox/vm/`` via ``--add-data``.
    """
    import sys  # noqa: PLC0415

    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "sandbox" / "vm"  # type: ignore[attr-defined]

    import hexagent  # noqa: PLC0415 — deferred to avoid circular import

    return Path(hexagent.__file__).parent.parent / "sandbox" / "vm"


def vm_lima_dir() -> Path:
    """Lima-specific VM config (``sandbox/vm/lima/``)."""
    return vm_dir() / "lima"


def vm_setup_dir() -> Path:
    """Shared VM setup scripts (``sandbox/vm/setup/``).

    These scripts are VM-engine-agnostic — they work on any Ubuntu/Debian
    system (Lima, WSL, cloud VMs, etc.).
    """
    return vm_dir() / "setup"
