"""Agent harness infrastructure.

This package contains modules that augment the agent loop:
- Environment detection
- Permission gating (safety rules, human-in-the-loop approval)
- Skill discovery and content loading
- System reminder rules for dynamic message annotation
"""

from hexagent.harness.definition import AgentDefinition
from hexagent.harness.environment import EnvironmentResolver
from hexagent.harness.model import ModelProfile
from hexagent.harness.permission import (
    PermissionDecision,
    PermissionGate,
    PermissionResult,
    SafetyRule,
)
from hexagent.harness.reminders import (
    BUILTIN_REMINDERS,
    Reminder,
    available_skills_reminder,
    evaluate_reminders,
    task_completion_reminder,
)
from hexagent.harness.skills import DEFAULT_SKILL_PATHS, SkillResolver

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
