"""Tracing for ClawWork.

Set environment variables to enable tracing — multiple platforms
work simultaneously::

    LANGSMITH_API_KEY    → LangSmith
    BRAINTRUST_API_KEY   → Braintrust

``@traced`` marks functions for tracing with every active platform.
When nothing is active it returns the original function — zero overhead.

``init_langchain_tracing()`` sets up LangChain callback hooks.

Example::

    from clawwork.trace import traced


    @traced
    def preprocess(data: str) -> str:
        return data.strip()
"""

from __future__ import annotations

import importlib
import logging
import os
from typing import TYPE_CHECKING, Any, TypeVar, overload

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

F = TypeVar("F", bound="Callable[..., Any]")

# Platform → (module, attribute) for the function-tracing decorator.
_TRACER_SPEC: dict[str, tuple[str, str]] = {
    "langsmith": ("langsmith", "traceable"),
    "braintrust": ("braintrust", "traced"),
}


def _detect_active() -> list[str]:
    """Return all platforms whose env vars are set."""
    active: list[str] = []
    if os.getenv("LANGSMITH_API_KEY") or (os.getenv("LANGCHAIN_API_KEY") and os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"):
        active.append("langsmith")
    if os.getenv("BRAINTRUST_API_KEY"):
        active.append("braintrust")
    return active


def _load_tracers(platforms: list[str]) -> list[Callable[..., Any]]:
    """Import each platform's function decorator.  Skip missing SDKs.

    For Braintrust, also calls ``init_logger()`` — without it
    ``@traced`` is a `no-op <https://www.braintrust.dev/docs/instrument/custom-tracing>`_.
    """
    tracers: list[Callable[..., Any]] = []
    for name in platforms:
        mod_path, attr = _TRACER_SPEC[name]
        try:
            mod = importlib.import_module(mod_path)
            tracers.append(getattr(mod, attr))
        except ImportError:
            logger.debug("%s SDK not installed, @traced will skip it", name)
            continue
        # Braintrust's @traced is a no-op until init_logger() is called.
        if name == "braintrust":
            try:
                mod.init_logger(project="ClawWork", api_key=os.getenv("BRAINTRUST_API_KEY"))
            except Exception:  # noqa: BLE001
                logger.debug("Failed to initialise Braintrust logger", exc_info=True)
    return tracers


# Auto-detect at import time.
_active = _detect_active()
_tracers = _load_tracers(_active)


def active_platforms() -> list[str]:
    """Return names of detected tracing platforms."""
    return list(_active)


@overload
def traced(fn: F) -> F: ...
@overload
def traced(*, name: str | None = ...) -> Callable[[F], F]: ...


def traced(
    fn: F | None = None,
    *,
    name: str | None = None,
) -> F | Callable[[F], F]:
    """Mark a function for tracing with all active platforms.

    Returns the original function when nothing is active — zero overhead.
    """

    def decorator(func: F) -> F:
        result = func
        for tracer in _tracers:
            result = tracer(name=name or func.__name__)(result)
        return result

    return decorator(fn) if fn is not None else decorator


_tracing_initialized = False


def init_langchain_tracing() -> None:
    """Set up LangChain tracing for active tracing platforms.

    Must be called before any LangChain models are created.  Lazy
    imports keep ``trace.py`` free of hard LangChain dependencies.
    Idempotent — repeated calls are no-ops.

    - **LangSmith** — sets ``LANGCHAIN_TRACING_V2=true``; LangChain auto-traces.
    - **Braintrust** — ``set_global_handler`` registers a ContextVar-based
      hook so LangChain picks up the handler automatically.
      ``init_logger`` is called here (not only at import time) so the
      logger is established in the same execution context as the handler.
    """
    global _tracing_initialized  # noqa: PLW0603
    if _tracing_initialized:
        return

    _tracing_initialized = True
    for platform in _active:
        if platform == "langsmith":
            os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")

        elif platform == "braintrust":
            try:
                import braintrust
                from braintrust_langchain import BraintrustCallbackHandler, set_global_handler

                braintrust.init_logger(project="ClawWork", api_key=os.getenv("BRAINTRUST_API_KEY"))
                set_global_handler(BraintrustCallbackHandler())
            except ImportError:
                logger.debug("braintrust-langchain not installed, skipping LangChain tracing")
