"""Core task registry for agent lifecycle management.

Framework-agnostic. Every agent — foreground or background — gets a
registry entry keyed by a stable ID. Producers register entries via
:meth:`TaskRegistry.register` (foreground) or :meth:`TaskRegistry.submit`
(background). Consumers read via :meth:`get` / :meth:`wait`, and the
reminder system calls :meth:`drain_completions` to deliver notifications
for background tasks only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from hexagent.types import ToolResult

if TYPE_CHECKING:
    from collections.abc import Coroutine

logger = logging.getLogger(__name__)

TaskStatus = Literal["running", "completed", "failed", "cancelled"]
"""Lifecycle states for a background task."""


@dataclass
class TaskEntry:
    """Mutable record tracking a single task (foreground or background)."""

    task_id: str
    kind: str
    description: str
    status: TaskStatus = "running"
    result: ToolResult | None = None
    completion_event: asyncio.Event = field(default_factory=asyncio.Event)
    asyncio_task: asyncio.Task[None] | None = field(default=None, repr=False)


@dataclass(frozen=True)
class TaskCompletion:
    """Frozen snapshot of a completed task, returned by :meth:`TaskRegistry.drain_completions`."""

    task_id: str
    kind: str
    description: str
    status: TaskStatus
    result: ToolResult


class TaskRegistry:
    """Unified registry for agent lifecycle.

    Every agent — foreground or background — gets an entry. The registry
    is pure bookkeeping: it doesn't execute domain logic, doesn't format
    results, and doesn't notify. Producers register entries via
    :meth:`register` (foreground) or :meth:`submit` (background).
    Consumers read via :meth:`get` / :meth:`wait`, and the reminder
    system calls :meth:`drain_completions` for background notifications.
    """

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._tasks: dict[str, TaskEntry] = {}
        self._completions: list[TaskCompletion] = []

    # ----- entry management ------------------------------------------------

    def register(self, task_id: str, kind: str, description: str) -> TaskEntry:
        """Create or reset a registry entry without an asyncio task.

        Use for foreground tasks where the caller manages execution.
        If *task_id* is new, creates a fresh ``"running"`` entry.
        If *task_id* exists and is terminal, resets to ``"running"``.

        Args:
            task_id: Caller-provided stable identifier.
            kind: Free-form label (``"agent"``, ``"bash"``, etc.).
            description: Human-readable task description.

        Returns:
            The (possibly reset) :class:`TaskEntry`.

        Raises:
            RuntimeError: If *task_id* is already in ``"running"`` state.
        """
        entry = self._tasks.get(task_id)
        if entry is not None:
            if entry.status == "running":
                msg = f"Task {task_id!r} is still running"
                raise RuntimeError(msg)
            # Reset terminal entry for reuse
            entry.kind = kind
            entry.description = description
            entry.status = "running"
            entry.result = None
            entry.completion_event = asyncio.Event()
            entry.asyncio_task = None
            return entry
        entry = TaskEntry(task_id=task_id, kind=kind, description=description)
        self._tasks[task_id] = entry
        return entry

    def submit(
        self,
        task_id: str,
        kind: str,
        description: str,
        coro: Coroutine[None, None, ToolResult],
    ) -> None:
        """Submit a coroutine as a background task.

        Creates (or resets) a registry entry and wraps the coroutine in
        an ``asyncio.Task``. The ``_run()`` wrapper handles lifecycle
        transitions and queues completion notifications.

        Args:
            task_id: Caller-provided stable identifier.
            kind: Free-form label (``"agent"``, ``"bash"``, etc.).
            description: Human-readable task description.
            coro: Coroutine that returns a :class:`ToolResult` on completion.

        Raises:
            RuntimeError: If *task_id* is already in ``"running"`` state.
        """
        entry = self.register(task_id, kind, description)
        entry.asyncio_task = asyncio.create_task(self._run(entry, coro))

    def complete(
        self,
        task_id: str,
        result: ToolResult,
        status: TaskStatus = "completed",
    ) -> None:
        """Finalise a foreground task.

        Unlike ``_run()`` (which handles background lifecycle), this does
        NOT append to ``_completions`` — foreground results are delivered
        inline, so no reminder notification is needed.

        Args:
            task_id: Task to finalise.
            result: The :class:`ToolResult` to store.
            status: Terminal status (default ``"completed"``).

        Raises:
            KeyError: If *task_id* is not known.
            RuntimeError: If entry is not in ``"running"`` state.
        """
        entry = self._tasks.get(task_id)
        if entry is None:
            msg = f"Task {task_id!r} not found"
            raise KeyError(msg)
        if entry.status != "running":
            msg = f"Task {task_id!r} is not running (status={entry.status!r})"
            raise RuntimeError(msg)
        entry.status = status
        entry.result = result
        entry.completion_event.set()

    async def _run(
        self,
        entry: TaskEntry,
        coro: Coroutine[None, None, ToolResult],
    ) -> None:
        """Internal wrapper that captures results and queues completions.

        CancelledError is a subclass of BaseException (not Exception) in
        Python 3.9+. The except blocks are ordered accordingly.
        """
        try:
            entry.result = await coro
            entry.status = "completed"
        except asyncio.CancelledError:
            entry.status = "cancelled"
            entry.result = ToolResult(error="Task was cancelled")
        except Exception as exc:
            logger.exception("Background task %s failed", entry.task_id)
            entry.status = "failed"
            entry.result = ToolResult(error=f"Task {entry.task_id} failed: {exc}")
        finally:
            entry.completion_event.set()
            if entry.status != "cancelled":
                self._completions.append(
                    TaskCompletion(
                        task_id=entry.task_id,
                        kind=entry.kind,
                        description=entry.description,
                        status=entry.status,
                        result=entry.result or ToolResult(error="Unknown error"),
                    ),
                )

    def get(self, task_id: str) -> TaskEntry | None:
        """Look up a task by ID. Returns ``None`` if not found."""
        return self._tasks.get(task_id)

    async def wait(self, task_id: str, *, timeout_ms: int) -> TaskEntry:
        """Block until a task reaches a terminal state.

        Args:
            task_id: Task to wait on.
            timeout_ms: Maximum wait time in milliseconds.

        Raises:
            KeyError: If *task_id* is not known.
            TimeoutError: If the task doesn't complete within *timeout_ms*.
        """
        entry = self._tasks.get(task_id)
        if entry is None:
            msg = f"Task {task_id!r} not found"
            raise KeyError(msg)
        await asyncio.wait_for(
            entry.completion_event.wait(),
            timeout=timeout_ms / 1000.0,
        )
        return entry

    def drain_completions(self) -> list[TaskCompletion]:
        """Return and clear pending completions. Idempotent."""
        completions = self._completions[:]
        self._completions.clear()
        return completions

    async def cancel(self, task_id: str) -> TaskEntry:
        """Cancel a running task.

        No-op if the task is already in a terminal state. The ``_run``
        wrapper handles ``CancelledError`` and sets ``status='cancelled'``.
        If the task was cancelled before ``_run`` had a chance to start,
        this method manually finalises the entry.

        Args:
            task_id: Task to cancel.

        Raises:
            KeyError: If *task_id* is not known.
        """
        entry = self._tasks.get(task_id)
        if entry is None:
            msg = f"Task {task_id!r} not found"
            raise KeyError(msg)
        if entry.status != "running":
            return entry
        if entry.asyncio_task is not None and not entry.asyncio_task.done():
            entry.asyncio_task.cancel()
            await asyncio.gather(entry.asyncio_task, return_exceptions=True)
        # _run may not have executed if the task was cancelled before it
        # was scheduled. Finalise the entry manually in that case.
        self._finalise_if_still_running(entry)
        return entry

    async def cancel_all(self) -> None:
        """Cancel all running tasks. For shutdown cleanup."""
        running = [e for e in self._tasks.values() if e.asyncio_task is not None and not e.asyncio_task.done()]
        for entry in running:
            assert entry.asyncio_task is not None  # noqa: S101
            entry.asyncio_task.cancel()
        if running:
            await asyncio.gather(
                *(e.asyncio_task for e in running if e.asyncio_task is not None),
                return_exceptions=True,
            )
        for entry in running:
            self._finalise_if_still_running(entry)

    def _finalise_if_still_running(self, entry: TaskEntry) -> None:
        """Set cancelled status on an entry that ``_run`` never reached."""
        if entry.status != "running":
            return
        entry.status = "cancelled"
        entry.result = ToolResult(error="Task was cancelled")
        entry.completion_event.set()
