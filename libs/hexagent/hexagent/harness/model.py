"""Model profile for context-aware compaction.

Wraps a resolved ``BaseChatModel`` with its context window size so
compaction thresholds are derived from actual model limits rather than
hardcoded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

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
            deployment.  ``None`` means the window size is unknown.
        compaction_threshold: Token count that triggers compaction.
            Resolved automatically by ``__post_init__``:

            * Explicitly provided → kept as-is.
            * ``context_window`` set, threshold omitted →
              ``int(0.75 * context_window)``.
            * Neither provided → stays ``None``.  The agent factory
              is responsible for applying a fallback and warning.

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

        Unknown context window (no derivation)::

            profile = ModelProfile(model=llm)
            # profile.compaction_threshold is None
    """

    model: BaseChatModel
    context_window: int | None = None
    compaction_threshold: int | None = None

    @property
    def name(self) -> str:
        """Human-readable model name."""
        return getattr(self.model, "model_name", type(self.model).__name__)

    def __post_init__(self) -> None:
        """Derive compaction_threshold from context_window when possible."""
        model_name = self.name
        if self.compaction_threshold is None and self.context_window is None:
            logger.warning(
                "[model: %s] Consider providing context_window and/or compaction_threshold in ModelProfile "
                "for reliable agent execution in long-running tasks.",
                model_name,
            )
        elif self.compaction_threshold is None and self.context_window is not None:
            derived = int(_DEFAULT_COMPACTION_RATIO * self.context_window)
            object.__setattr__(self, "compaction_threshold", derived)
            logger.info(
                "[model: %s] compaction_threshold not specified; defaults to %.0f%% of context_window (%s tokens).",
                model_name,
                _DEFAULT_COMPACTION_RATIO * 100,
                f"{derived:,}",
            )
