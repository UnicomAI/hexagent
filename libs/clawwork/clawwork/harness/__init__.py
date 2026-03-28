"""Agent harness infrastructure.

This package contains modules that augment the agent loop:
- Environment detection
- Permission gating (safety rules, human-in-the-loop approval)
- Skill discovery and content loading
- System reminder rules for dynamic message annotation
"""

from clawwork.harness.definition import AgentDefinition
from clawwork.harness.environment import EnvironmentResolver
from clawwork.harness.model import ModelProfile
from clawwork.harness.permission import (
    PermissionDecision,
    PermissionGate,
    PermissionResult,
    SafetyRule,
)
from clawwork.harness.reminders import (
    BUILTIN_REMINDERS,
    Reminder,
    available_skills_reminder,
    evaluate_reminders,
    task_completion_reminder,
)
from clawwork.harness.skills import DEFAULT_SKILL_PATHS, SkillResolver

__all__ = [
    "BUILTIN_REMINDERS",
    "DEFAULT_SKILL_PATHS",
    "AgentDefinition",
    "EnvironmentResolver",
    "ModelProfile",
    "PermissionDecision",
    "PermissionGate",
    "PermissionResult",
    "Reminder",
    "SafetyRule",
    "SkillResolver",
    "available_skills_reminder",
    "evaluate_reminders",
    "task_completion_reminder",
]
