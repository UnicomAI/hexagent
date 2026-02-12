"""Tests for ModelProfile."""

# ruff: noqa: PLR2004

from __future__ import annotations

import pytest

from openagent.harness.model import _DEFAULT_COMPACTION_RATIO, ModelProfile


class TestModelProfile:
    def test_derives_compaction_threshold_from_context_window(self) -> None:
        profile = ModelProfile(model="openai:gpt-5.2", context_window=128_000)
        assert profile.compaction_threshold == int(_DEFAULT_COMPACTION_RATIO * 128_000)

    def test_explicit_compaction_threshold(self) -> None:
        profile = ModelProfile(
            model="openai:gpt-5.2",
            context_window=128_000,
            compaction_threshold=80_000,
        )
        assert profile.compaction_threshold == 80_000

    def test_frozen(self) -> None:
        profile = ModelProfile(model="openai:gpt-5.2", context_window=128_000)
        with pytest.raises(AttributeError):
            profile.context_window = 256_000  # type: ignore[misc]

    def test_accepts_model_string(self) -> None:
        profile = ModelProfile(model="anthropic:claude-sonnet", context_window=200_000)
        assert profile.model == "anthropic:claude-sonnet"

    def test_context_window_required(self) -> None:
        with pytest.raises(TypeError):
            ModelProfile(model="openai:gpt-5.2")  # type: ignore[call-arg]
