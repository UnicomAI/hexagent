"""Context management types and compaction protocol.

This module provides framework-agnostic types for message transformations
and a stateless CompactionController that encapsulates the 3-phase
compaction state machine.

Design principles:
- Zero framework imports — only stdlib and typing.
- Zero mutable state — phase flows in/out as arguments.
- Mutually exclusive operations — enforced via ContextUpdate union type.

Any agent loop (LangChain, custom, or future framework) integrates by:
1. Calling ``pre_model_update`` before each model call.
2. Calling ``post_model_transition`` after each model response.
3. Translating the returned ``ContextUpdate`` into framework-specific
   message operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

DEFAULT_COMPACTION_THRESHOLD = 100_000


# ---------------------------------------------------------------------------
# Context update types — the contract
# ---------------------------------------------------------------------------


class CompactionPhase(str, Enum):
    """State machine phases for context compaction.

    The compaction process spans 3 iterations through the agent loop:

    1. NONE → REQUESTING: Token count exceeds threshold, request a summary.
    2. REQUESTING → APPLYING: LLM generated a summary, apply it.
    3. APPLYING → NONE: Replace messages with summary, resume normal operation.
    """

    NONE = "none"
    REQUESTING = "requesting"
    APPLYING = "applying"


@dataclass(frozen=True)
class Overwrite:
    """Signal to replace all messages with a compacted summary.

    This is an empty signal — the actual summary content lives in
    the conversation state (the last model response). The agent loop
    extracts it and rebuilds messages.
    """


@dataclass(frozen=True)
class Append:
    """Append a new message to the conversation.

    Attributes:
        content: The message text.
        role: The message role. Default ``"user"``.
    """

    content: str
    role: str = "user"


@dataclass(frozen=True)
class Inject:
    """Inject content into the last message.

    Attributes:
        content: The text to inject.
        position: Where to inject — ``"prepend"`` or ``"append"``.
            Default ``"prepend"``.
    """

    content: str
    position: Literal["prepend", "append"] = "prepend"


ContextUpdate = Overwrite | Append | Inject
"""A message transformation. Only one operation happens per hook call."""


# ---------------------------------------------------------------------------
# CompactionController — stateless protocol
# ---------------------------------------------------------------------------


class CompactionController:
    """Stateless compaction protocol. Phase passed in, phase returned out.

    Encapsulates the 3-phase compaction state machine so that any agent
    loop gets correct behavior by calling two methods. No mutable state —
    concurrency-safe by construction.

    Examples:
        Basic integration in a middleware / agent loop::

            controller = CompactionController(
                compaction_prompt=library.get("compaction/request"),
            )

            # Before each model call:
            update, new_phase = controller.pre_model_update(phase)

            # After each model response:
            should_rerun, new_phase = controller.post_model_transition(
                token_count,
                phase,
            )
    """

    def __init__(
        self,
        compaction_prompt: str,
        *,
        threshold: int = DEFAULT_COMPACTION_THRESHOLD,
    ) -> None:
        """Initialize the controller.

        Args:
            compaction_prompt: Prompt sent to the LLM to request a summary.
                Canonical source: ``compaction/request.md`` in the
                PromptLibrary.
            threshold: Token count that triggers compaction.
        """
        self._threshold = threshold
        self._compaction_prompt = compaction_prompt

    @property
    def threshold(self) -> int:
        """The token threshold that triggers compaction."""
        return self._threshold

    @property
    def compaction_prompt(self) -> str:
        """The prompt used to request a conversation summary."""
        return self._compaction_prompt

    def pre_model_update(
        self,
        phase: CompactionPhase,
    ) -> tuple[ContextUpdate | None, CompactionPhase]:
        """Determine what to do to messages before calling the model.

        Args:
            phase: The current compaction phase from conversation state.

        Returns:
            A ``(update, new_phase)`` tuple:

            - REQUESTING → ``(Append(compaction_prompt), REQUESTING)``
            - APPLYING → ``(Overwrite(), NONE)``
            - NONE → ``(None, NONE)``
        """
        if phase == CompactionPhase.REQUESTING:
            return Append(content=self._compaction_prompt, role="user"), phase

        if phase == CompactionPhase.APPLYING:
            return Overwrite(), CompactionPhase.NONE

        return None, phase

    def post_model_transition(
        self,
        token_count: int,
        phase: CompactionPhase,
    ) -> tuple[bool, CompactionPhase]:
        """Determine whether to loop back and what phase to enter.

        Args:
            token_count: Current token count of the conversation.
            phase: The current compaction phase from conversation state.

        Returns:
            A ``(should_rerun, new_phase)`` tuple:

            - NONE + threshold exceeded → ``(True, REQUESTING)``
            - REQUESTING → ``(True, APPLYING)``
            - otherwise → ``(False, phase)``
        """
        if phase == CompactionPhase.NONE and token_count >= self._threshold:
            return True, CompactionPhase.REQUESTING

        if phase == CompactionPhase.REQUESTING:
            return True, CompactionPhase.APPLYING

        return False, phase
