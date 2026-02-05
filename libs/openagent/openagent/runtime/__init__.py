"""Runtime infrastructure modules for OpenAgent.

This package contains framework-agnostic modules that manage
agent runtime behavior:

- Context types (Overwrite, Append, Inject): Message transformation contract
- CompactionController: Stateless 3-phase compaction protocol
- CapabilityRegistry: Stores tools, skills, and MCP servers (pure data)
- PermissionGate: Validates tool calls and handles approvals

Prompt infrastructure lives in ``openagent.prompts``.
"""

from openagent.runtime.context import (
    Append,
    CompactionController,
    CompactionPhase,
    ContextUpdate,
    Inject,
    Overwrite,
)
from openagent.runtime.permission import (
    PermissionDecision,
    PermissionGate,
    PermissionResult,
    SafetyRule,
)
from openagent.runtime.registry import CapabilityRegistry

__all__ = [
    "Append",
    "CapabilityRegistry",
    "CompactionController",
    "CompactionPhase",
    "ContextUpdate",
    "Inject",
    "Overwrite",
    "PermissionDecision",
    "PermissionGate",
    "PermissionResult",
    "SafetyRule",
]
