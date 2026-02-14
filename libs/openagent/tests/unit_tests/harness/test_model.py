"""Tests for ModelProfile."""

# ruff: noqa: PLR2004

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import BaseChatModel

from openagent.harness.model import (
    _DEFAULT_COMPACTION_RATIO,
    ModelProfile,
)


def _stub_model(name: str = "test-model") -> BaseChatModel:
    """Minimal BaseChatModel stub for unit tests."""
    mock = MagicMock(spec=BaseChatModel)
    mock.model_name = name
    return mock


class TestModelProfile:
    def test_derives_compaction_threshold_from_context_window(self) -> None:
        profile = ModelProfile(model=_stub_model(), context_window=128_000)
        assert profile.compaction_threshold == int(_DEFAULT_COMPACTION_RATIO * 128_000)

    def test_explicit_compaction_threshold(self) -> None:
        profile = ModelProfile(
            model=_stub_model(),
            context_window=128_000,
            compaction_threshold=80_000,
        )
        assert profile.compaction_threshold == 80_000

    def test_frozen(self) -> None:
        profile = ModelProfile(model=_stub_model(), context_window=128_000)
        with pytest.raises(AttributeError):
            profile.context_window = 256_000  # type: ignore[misc]

    def test_context_window_defaults_to_none(self) -> None:
        profile = ModelProfile(model=_stub_model())
        assert profile.context_window is None
        assert profile.compaction_threshold is None

    def test_no_derivation_without_context_window(self) -> None:
        profile = ModelProfile(model=_stub_model())
        assert profile.compaction_threshold is None
