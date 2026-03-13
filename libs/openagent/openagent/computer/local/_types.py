"""Internal types for the local computer module."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResolvedMount:
    """A fully resolved mount with concrete host and guest paths.

    This is an internal type — framework users work with ``Mount``.
    """

    host_path: str
    guest_path: str
    writable: bool = False
