"""Tests for harness/permission.py — PermissionGate, SafetyRule."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hexagent.harness.permission import (
    PermissionDecision,
    PermissionGate,
    PermissionResult,
    SafetyRule,
)

if TYPE_CHECKING:
    from typing import Any


# ---------------------------------------------------------------------------
# Concrete rules for testing
# ---------------------------------------------------------------------------


class AlwaysDenyRule(SafetyRule):
    """Denies every tool call."""

    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision:
        return PermissionDecision(result=PermissionResult.DENIED, reason="blocked")


class RequireApprovalRule(SafetyRule):
    """Requires human approval for every tool call."""

    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision:
        return PermissionDecision(
            result=PermissionResult.NEEDS_APPROVAL,
            approval_prompt="Please approve this action.",
        )


class PassthroughRule(SafetyRule):
    """Returns None — rule does not apply."""

    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision | None:
        return None


class BlockBashRmRule(SafetyRule):
    """Denies bash calls containing 'rm -rf', passes everything else."""

    def check(self, tool_name: str, tool_args: dict[str, Any]) -> PermissionDecision | None:
        if tool_name == "bash" and "rm -rf" in tool_args.get("command", ""):
            return PermissionDecision(result=PermissionResult.DENIED, reason="Destructive command")
        return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPermissionResult:
    def test_enum_values(self) -> None:
        assert PermissionResult.ALLOWED.value == "allowed"
        assert PermissionResult.DENIED.value == "denied"
        assert PermissionResult.NEEDS_APPROVAL.value == "needs_approval"


class TestPermissionDecision:
    def test_defaults(self) -> None:
        d = PermissionDecision(result=PermissionResult.ALLOWED)
        assert d.reason is None
        assert d.approval_prompt is None

    def test_with_reason(self) -> None:
        d = PermissionDecision(result=PermissionResult.DENIED, reason="blocked")
        assert d.reason == "blocked"


class TestPermissionGate:
    async def test_no_rules_returns_allowed(self) -> None:
        gate = PermissionGate()
        decision = await gate.check("bash", {"command": "echo hi"})
        assert decision.result == PermissionResult.ALLOWED

    async def test_deny_rule_blocks_call(self) -> None:
        gate = PermissionGate()
        gate.register_rule(AlwaysDenyRule())
        decision = await gate.check("bash", {"command": "echo hi"})
        assert decision.result == PermissionResult.DENIED
        assert decision.reason == "blocked"

    async def test_needs_approval_rule(self) -> None:
        gate = PermissionGate()
        gate.register_rule(RequireApprovalRule())
        decision = await gate.check("read", {"file_path": "/etc/passwd"})
        assert decision.result == PermissionResult.NEEDS_APPROVAL
        assert decision.approval_prompt is not None

    async def test_first_matching_rule_wins(self) -> None:
        gate = PermissionGate()
        gate.register_rule(AlwaysDenyRule())
        gate.register_rule(RequireApprovalRule())
        decision = await gate.check("bash", {})
        assert decision.result == PermissionResult.DENIED  # first rule wins

    async def test_passthrough_rule_skipped(self) -> None:
        gate = PermissionGate()
        gate.register_rule(PassthroughRule())
        decision = await gate.check("bash", {})
        assert decision.result == PermissionResult.ALLOWED

    async def test_passthrough_then_deny(self) -> None:
        gate = PermissionGate()
        gate.register_rule(PassthroughRule())
        gate.register_rule(AlwaysDenyRule())
        decision = await gate.check("bash", {})
        assert decision.result == PermissionResult.DENIED

    async def test_selective_rule_only_blocks_matching_calls(self) -> None:
        gate = PermissionGate()
        gate.register_rule(BlockBashRmRule())

        safe = await gate.check("bash", {"command": "echo hi"})
        assert safe.result == PermissionResult.ALLOWED

        dangerous = await gate.check("bash", {"command": "rm -rf /"})
        assert dangerous.result == PermissionResult.DENIED

    async def test_clear_rules_removes_all(self) -> None:
        gate = PermissionGate()
        gate.register_rule(AlwaysDenyRule())
        gate.clear_rules()
        decision = await gate.check("bash", {})
        assert decision.result == PermissionResult.ALLOWED
