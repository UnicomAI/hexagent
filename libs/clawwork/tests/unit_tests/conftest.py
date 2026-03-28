"""Shared test fixtures for unit tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from clawwork.harness.model import ModelProfile
from clawwork.tasks import TaskRegistry
from clawwork.tools.base import BaseAgentTool
from clawwork.types import ToolResult

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def _stub_model() -> MagicMock:
    mock = MagicMock()
    mock.model_name = "stub-model"
    return mock


STUB_PROFILE = ModelProfile(model=_stub_model(), compaction_threshold=100_000)
"""Reusable ModelProfile for tests that don't care about model identity."""


class StubParams(BaseModel):
    """Minimal parameter schema for mock tools."""

    arg: str = ""


def make_tool(name: str, *, instruction: str = "") -> BaseAgentTool[StubParams]:
    """Create a stub tool with the given name.

    Use this instead of writing per-tool mock classes.
    """

    class _Tool(BaseAgentTool[StubParams]):
        args_schema = StubParams

        async def execute(self, params: StubParams) -> ToolResult:
            return ToolResult(output="")

    _Tool.name = name
    _Tool.instruction = instruction
    return _Tool()


def core_tools() -> list[BaseAgentTool[Any]]:
    """Return the six core mock tools (Bash, Read, Edit, Write, Glob, Grep)."""
    return [make_tool(n) for n in ("Bash", "Read", "Edit", "Write", "Glob", "Grep")]


@pytest.fixture
async def task_registry() -> AsyncIterator[TaskRegistry]:
    """TaskRegistry with automatic cleanup of running tasks."""
    registry = TaskRegistry()
    yield registry
    await registry.cancel_all()
