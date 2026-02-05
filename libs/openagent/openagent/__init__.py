"""OpenAgent package.

OpenAgent is an Agent SDK (supporting OpenAI-compatible LLMs) similar to
Anthropic's Claude Agent SDK.

Core Philosophy: Give agents a CLI-based computer, allowing them to work
like humans do.
"""

from openagent.langchain import create_agent
from openagent.prompts import PromptLibrary, SystemPromptAssembler
from openagent.runtime import (
    Append,
    CapabilityRegistry,
    CompactionController,
    CompactionPhase,
    Inject,
    Overwrite,
    PermissionDecision,
    PermissionGate,
    PermissionResult,
    SafetyRule,
)

__all__ = [
    "Append",
    "CapabilityRegistry",
    "CompactionController",
    "CompactionPhase",
    "Inject",
    "Overwrite",
    "PermissionDecision",
    "PermissionGate",
    "PermissionResult",
    "PromptLibrary",
    "SafetyRule",
    "SystemPromptAssembler",
    "create_agent",
]
