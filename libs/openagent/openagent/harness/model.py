"""Model profile for context-aware compaction.

Wraps a model specifier with its context window size so compaction
thresholds are derived from actual model limits rather than hardcoded.
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
        model: Model specifier (``"openai:gpt-5.2"``) or pre-configured instance.
        context_window: Maximum context window in tokens for this deployment.
        compaction_threshold: Token count that triggers compaction.
            Defaults to ``int(0.75 * context_window)``.

    Examples:
        Derive threshold automatically::

            profile = ModelProfile(model="openai:gpt-5.2", context_window=128_000)
            # profile.compaction_threshold == 96_000

        Override threshold explicitly::

            profile = ModelProfile(
                model="openai:gpt-5.2",
                context_window=128_000,
                compaction_threshold=80_000,
            )
    """

    model: str | BaseChatModel
    context_window: int
    compaction_threshold: int | None = None

    def __post_init__(self) -> None:
        """Derive compaction_threshold from context_window if not set."""
        if self.compaction_threshold is None:
            object.__setattr__(
                self,
                "compaction_threshold",
                int(_DEFAULT_COMPACTION_RATIO * self.context_window),
            )
