"""Agent harness infrastructure.

This package contains modules that augment the agent loop:
- Permission gating (safety rules, human-in-the-loop approval)
- Skill discovery and content loading
- System reminder rules for dynamic message annotation
"""

from openagent.harness.model import ModelProfile
from openagent.harness.permission import (
    PermissionDecision,
    PermissionGate,
    PermissionResult,
    SafetyRule,
)
from openagent.harness.reminders import (
    BUILTIN_REMINDERS,
    Reminder,
    evaluate_reminders,
    initial_available_skills,
)
from openagent.harness.skills import DEFAULT_SKILL_PATHS, SkillResolver

__all__ = [
    "BUILTIN_REMINDERS",
    "DEFAULT_SKILL_PATHS",
    "ModelProfile",
    "PermissionDecision",
    "PermissionGate",
    "PermissionResult",
    "Reminder",
    "SafetyRule",
    "SkillResolver",
    "evaluate_reminders",
    "initial_available_skills",
]
