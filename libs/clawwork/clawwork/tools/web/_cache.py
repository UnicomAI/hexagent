"""Caching utilities for web tools.

Provides simple TTL-based caching for fetch and search results.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any

from cachetools import TTLCache

if TYPE_CHECKING:
    from clawwork.tools.web.providers.fetch.base import FetchResult
    from clawwork.tools.web.providers.search.base import SearchResult

# Default TTL: 15 minutes
DEFAULT_TTL_SECONDS = 900

# Module-level caches (shared across all tool instances)
_fetch_cache: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=DEFAULT_TTL_SECONDS)
_search_cache: TTLCache[str, Any] = TTLCache(maxsize=100, ttl=DEFAULT_TTL_SECONDS)


def cache_key(*args: str) -> str:
    """Generate a short cache key from arguments.

    Uses null byte separator to avoid collisions when arguments contain
    the separator character (null bytes are invalid in URLs and queries).

    Args:
        *args: String arguments to hash.

    Returns:
        A 16-character hex string.
    """
    return hashlib.sha256("\x00".join(args).encode()).hexdigest()[:16]


def get_fetch_cache() -> TTLCache[str, FetchResult]:
    """Get the shared fetch result cache."""
    return _fetch_cache


def get_search_cache() -> TTLCache[str, SearchResult]:
    """Get the shared search result cache."""
    return _search_cache


def clear_caches() -> None:
    """Clear all caches. Useful for testing."""
    _fetch_cache.clear()
    _search_cache.clear()
