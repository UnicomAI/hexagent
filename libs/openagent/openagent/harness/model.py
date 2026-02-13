"""Model profile for context-aware compaction.

Wraps a resolved ``BaseChatModel`` with its context window size so
compaction thresholds are derived from actual model limits rather than
hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

_DEFAULT_COMPACTION_RATIO = 0.75
_FALLBACK_COMPACTION_THRESHOLD = 100_000


@dataclass(frozen=True)
class ModelProfile:
    """Model configuration with context-window-aware compaction.

    Attributes:
        model: A pre-configured ``BaseChatModel`` instance.  String-based
            resolution (e.g. ``"openai:gpt-5.2"``) belongs in the agent
            factory — pass a resolved model here.
        context_window: Maximum context window in tokens for this
            deployment.  ``None`` means the window size is unknown; the
            system falls back to ``_FALLBACK_COMPACTION_THRESHOLD``.
        compaction_threshold: Token count that triggers compaction.
            Resolved automatically by ``__post_init__``:

            * Explicitly provided → kept as-is.
            * ``context_window`` set, threshold omitted →
              ``int(0.75 * context_window)``.
            * Neither provided → ``_FALLBACK_COMPACTION_THRESHOLD``
              (100 000).

    Examples:
        Derive threshold from context window::

            from langchain.chat_models import init_chat_model

            llm = init_chat_model("openai:gpt-5.2")
            profile = ModelProfile(model=llm, context_window=128_000)
            # profile.compaction_threshold == 96_000

        Override threshold explicitly::

            profile = ModelProfile(
                model=llm,
                context_window=128_000,
                compaction_threshold=80_000,
            )

        Unknown context window (fallback)::

            profile = ModelProfile(model=llm)
            # profile.compaction_threshold == 100_000
    """

    model: BaseChatModel
    context_window: int | None = None
    compaction_threshold: int | None = None

    def __post_init__(self) -> None:
        """Derive compaction_threshold when not explicitly set."""
        if self.compaction_threshold is None:
            if self.context_window is not None:
                object.__setattr__(
                    self,
                    "compaction_threshold",
                    int(_DEFAULT_COMPACTION_RATIO * self.context_window),
                )
            else:
                object.__setattr__(
                    self,
                    "compaction_threshold",
                    _FALLBACK_COMPACTION_THRESHOLD,
                )
