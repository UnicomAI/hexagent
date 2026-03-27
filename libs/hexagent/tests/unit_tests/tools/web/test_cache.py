"""Tests for cache utilities."""

from __future__ import annotations

from hexagent.tools.web._cache import (
    cache_key,
    clear_caches,
    get_fetch_cache,
    get_search_cache,
)
from hexagent.tools.web.providers.fetch import FetchResult
from hexagent.tools.web.providers.search import SearchResult


class TestCacheKey:
    """Tests for cache_key function."""

    def test_same_inputs_produce_same_key(self) -> None:
        """Identical inputs produce identical keys."""
        key1 = cache_key("query", "10")
        key2 = cache_key("query", "10")
        assert key1 == key2

    def test_different_inputs_produce_different_keys(self) -> None:
        """Different inputs produce different keys."""
        key1 = cache_key("query1", "10")
        key2 = cache_key("query2", "10")
        assert key1 != key2

    def test_input_order_matters(self) -> None:
        """Argument order affects the key."""
        key1 = cache_key("a", "b")
        key2 = cache_key("b", "a")
        assert key1 != key2

    def test_provider_affects_cache_key(self) -> None:
        """Different providers produce different keys for same query."""
        key1 = cache_key("tavily", "query", "10")
        key2 = cache_key("brave", "query", "10")
        assert key1 != key2

    def test_arguments_with_pipe_do_not_collide(self) -> None:
        """Arguments containing special characters don't cause collisions."""
        # These would collide if using "|" as separator
        key1 = cache_key("a|b", "c")
        key2 = cache_key("a", "b|c")
        assert key1 != key2


class TestClearCaches:
    """Tests for clear_caches function."""

    def test_clears_items_from_both_caches(self) -> None:
        """Both fetch and search caches are cleared."""
        fetch_cache = get_fetch_cache()
        search_cache = get_search_cache()

        # Add items to caches
        fetch_cache["test_key"] = FetchResult(content="test", url="http://x", title=None)
        search_cache["test_key"] = SearchResult(items=[])

        assert len(fetch_cache) == 1
        assert len(search_cache) == 1

        clear_caches()

        assert len(fetch_cache) == 0
        assert len(search_cache) == 0
