"""Declarative agent definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

    from hexagent.harness.model import ModelProfile


@dataclass(frozen=True)
class AgentDefinition:
    """Declarative subagent specification.

    Describes what a subagent IS without any runtime state.
    The agent factory resolves models and validates tool names eagerly.
    """

    description: str
    system_prompt: str = ""
    tools: tuple[str, ...] = ()
    model: str | BaseChatModel | ModelProfile | None = None
