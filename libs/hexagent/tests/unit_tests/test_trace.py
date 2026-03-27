"""Tests for hexagent.trace and LangChain tracing setup."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

import pytest

import hexagent.trace as trc

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clean module state and relevant env vars between tests."""
    for var in (
        "LANGSMITH_API_KEY",
        "LANGCHAIN_API_KEY",
        "LANGCHAIN_TRACING_V2",
        "BRAINTRUST_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    trc._active = []
    trc._tracers = []
    trc._tracing_initialized = False
    yield
    trc._active = []
    trc._tracers = []
    trc._tracing_initialized = False


class TestDetectActive:
    """Multi-platform detection from env vars."""

    def test_empty_when_no_vars(self) -> None:
        assert trc._detect_active() == []

    def test_langsmith_via_dedicated_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSMITH_API_KEY", "k")
        assert trc._detect_active() == ["langsmith"]

    def test_langsmith_via_langchain_key_and_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
        assert trc._detect_active() == ["langsmith"]

    def test_langchain_key_alone_not_enough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGCHAIN_API_KEY", "k")
        assert trc._detect_active() == []

    def test_both(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LANGSMITH_API_KEY", "k")
        monkeypatch.setenv("BRAINTRUST_API_KEY", "k")
        assert trc._detect_active() == ["langsmith", "braintrust"]


class TestLoadTracers:
    """Tracer import from platform SDKs."""

    def test_empty_for_no_platforms(self) -> None:
        assert trc._load_tracers([]) == []

    def test_skips_missing_sdk(self) -> None:
        with patch.dict("sys.modules", {"langsmith": None}):
            assert trc._load_tracers(["langsmith"]) == []

    def test_loads_installed_sdk(self) -> None:
        mock_sdk = MagicMock()
        with patch.dict("sys.modules", {"langsmith": mock_sdk}):
            result = trc._load_tracers(["langsmith"])
        assert result == [mock_sdk.traceable]

    def test_loads_multiple_skips_missing(self) -> None:
        mock_sdk = MagicMock()
        with patch.dict("sys.modules", {"langsmith": mock_sdk, "braintrust": None}):
            result = trc._load_tracers(["langsmith", "braintrust"])
        assert result == [mock_sdk.traceable]

    def test_braintrust_calls_init_logger(self) -> None:
        mock_bt = MagicMock()
        with patch.dict("sys.modules", {"braintrust": mock_bt}):
            trc._load_tracers(["braintrust"])
        mock_bt.init_logger.assert_called_once()

    def test_braintrust_init_logger_failure_is_non_fatal(self) -> None:
        mock_bt = MagicMock()
        mock_bt.init_logger.side_effect = RuntimeError("boom")
        with patch.dict("sys.modules", {"braintrust": mock_bt}):
            result = trc._load_tracers(["braintrust"])
        # Tracer is still loaded even if init_logger fails.
        assert result == [mock_bt.traced]


class TestActivePlatforms:
    """The active_platforms() public API."""

    def test_returns_copy(self) -> None:
        trc._active = ["langsmith"]
        result = trc.active_platforms()
        result.append("extra")
        assert trc._active == ["langsmith"]


class TestTraced:
    """The @traced decorator."""

    def test_returns_original_when_no_tracers(self) -> None:
        def func() -> int:
            return 1

        assert trc.traced(func) is func

    def test_returns_original_with_name_kwarg(self) -> None:
        def func() -> int:
            return 1

        assert trc.traced(name="span")(func) is func

    def test_parentheses_optional(self) -> None:
        def func() -> int:
            return 1

        assert trc.traced(func) is func
        assert trc.traced()(func) is func

    def test_delegates_to_single_tracer(self) -> None:
        wrapped: Any = MagicMock()
        factory: Any = MagicMock(return_value=wrapped)
        trc._tracers = [factory]

        def func() -> None:
            pass

        result = trc.traced(func)
        factory.assert_called_once_with(name="func")
        wrapped.assert_called_once_with(func)
        assert result is wrapped.return_value

    def test_chains_multiple_tracers(self) -> None:
        first_wrapped: Any = MagicMock(name="first_wrapped")
        first_result: Any = MagicMock(name="first_result")
        first_wrapped.return_value = first_result
        first: Any = MagicMock(return_value=first_wrapped)

        second_wrapped: Any = MagicMock(name="second_wrapped")
        second_result: Any = MagicMock(name="second_result")
        second_wrapped.return_value = second_result
        second: Any = MagicMock(return_value=second_wrapped)

        trc._tracers = [first, second]

        def func() -> None:
            pass

        result = trc.traced(func)

        first.assert_called_once_with(name="func")
        first_wrapped.assert_called_once_with(func)
        second.assert_called_once_with(name="func")
        second_wrapped.assert_called_once_with(first_result)
        assert result is second_result

    def test_custom_name_forwarded(self) -> None:
        factory: Any = MagicMock(return_value=MagicMock())
        trc._tracers = [factory]

        def func() -> None:
            pass

        trc.traced(name="custom")(func)
        factory.assert_called_once_with(name="custom")

    async def test_async_passthrough(self) -> None:
        @trc.traced
        async def add(a: int, b: int) -> int:
            return a + b

        assert await add(1, 2) == 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# LangChain tracing setup (lives in trace.py)
# ---------------------------------------------------------------------------


class TestLangchainTracing:
    """LangChain-specific tracing initialisation."""

    @pytest.fixture(autouse=True)
    def _reset_callbacks(self) -> Iterator[None]:
        trc._tracing_initialized = False
        yield
        trc._tracing_initialized = False

    def test_noop_when_no_platforms(self) -> None:
        trc.init_langchain_tracing()
        assert trc._tracing_initialized is True

    def test_langsmith_sets_tracing_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
        trc._active = ["langsmith"]

        trc.init_langchain_tracing()

        import os

        assert os.environ["LANGCHAIN_TRACING_V2"] == "true"

    def test_braintrust_sets_global_handler(self) -> None:
        mock_handler = MagicMock()
        mock_bt_lc = MagicMock()
        mock_bt_lc.BraintrustCallbackHandler.return_value = mock_handler
        mock_bt = MagicMock()
        trc._active = ["braintrust"]

        with patch.dict("sys.modules", {"braintrust": mock_bt, "braintrust_langchain": mock_bt_lc}):
            trc.init_langchain_tracing()

        mock_bt.init_logger.assert_called_once()
        mock_bt_lc.set_global_handler.assert_called_once_with(mock_handler)

    def test_braintrust_skipped_when_not_installed(self) -> None:
        trc._active = ["braintrust"]
        with patch.dict("sys.modules", {"braintrust": MagicMock(), "braintrust_langchain": None}):
            trc.init_langchain_tracing()
        assert trc._tracing_initialized is True

    def test_only_initialises_once(self) -> None:
        trc._active = ["langsmith"]
        trc.init_langchain_tracing()
        assert trc._tracing_initialized is True
        # Second call is a no-op — changing _active has no effect.
        trc._active = ["langsmith", "braintrust"]
        trc.init_langchain_tracing()
        # Still initialized, but braintrust was never set up.
        assert trc._tracing_initialized is True
