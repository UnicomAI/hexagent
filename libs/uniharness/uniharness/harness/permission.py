"""Permission gate for safety validation and human approval.

This module provides the PermissionGate class which validates tool calls
against safety rules and handles human-in-the-loop approval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PermissionResult(Enum):
    """Result of a permission check."""

    ALLOWED = "allowed"
    DENIED = "denied"
    NEEDS_APPROVAL = "needs_approval"


@dataclass
class PermissionDecision:
    """Decision from a permission check.

    Attributes:
        result: The permission result (allowed, denied, needs_approval).
        reason: Optional explanation for the decision.
        approval_prompt: Optional prompt for human approval (when needs_approval).
    """

    result: PermissionResult
    reason: str | None = None
    approval_prompt: str | None = None


class SafetyRule(ABC):
    """Abstract base class for safety rules.

    Safety rules are checked before tool execution.
    Implement this class to create custom safety rules.

    Examples:
        ```python
        class BlockRmRfRule(SafetyRule):
            def check(self, tool_name: str, tool_args: dict) -> PermissionDecision | None:
                if tool_name == "bash":
                    cmd = tool_args.get("command", "")
                    if "rm -rf" in cmd:
                        return PermissionDecision(
                            result=PermissionResult.DENIED,
                            reason="Destructive command blocked: rm -rf",
                        )
                return None  # Rule doesn't apply
        ```
    """

    @abstractmethod
    def check(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> PermissionDecision | None:
        """Check if a tool call is allowed.

        Args:
            tool_name: The name of the tool being called.
            tool_args: The arguments passed to the tool.

        Returns:
            PermissionDecision if this rule applies, None otherwise.
            When None is returned, the check continues to the next rule.
        """
        ...


class PermissionGate:
    """Gates tool execution based on safety rules.

    Validates tool calls against registered safety rules.
    Returns ALLOWED if no rules deny or require approval.

    Examples:
        ```python
        gate = PermissionGate()

        # Register a custom rule
        gate.register_rule(BlockRmRfRule())

        # Check a tool call
        decision = await gate.check("bash", {"command": "rm -rf /"})
        if decision.result == PermissionResult.DENIED:
            print(f"Blocked: {decision.reason}")
        ```
    """

    def __init__(self) -> None:
        """Initialize an empty permission gate."""
        self._rules: list[SafetyRule] = []

    def register_rule(self, rule: SafetyRule) -> None:
        """Register a safety rule.

        Rules are checked in registration order.

        Args:
            rule: The safety rule to register.
        """
        self._rules.append(rule)

    def clear_rules(self) -> None:
        """Clear all registered rules."""
        self._rules.clear()

    async def check(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
    ) -> PermissionDecision:
        """Check if a tool call is allowed.

        Checks all registered rules in order. Returns the first
        non-None decision, or ALLOWED if no rules apply.

        Args:
            tool_name: The name of the tool being called.
            tool_args: The arguments passed to the tool.

        Returns:
            PermissionDecision indicating if the call is allowed.
        """
        for rule in self._rules:
            decision = rule.check(tool_name, tool_args)
            if decision is not None:
                return decision

        # No rules blocked or required approval
        return PermissionDecision(result=PermissionResult.ALLOWED)
