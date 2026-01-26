"""Base classes for Computer abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

if TYPE_CHECKING:
    from openagent.types import CLIResult

# Timeout constants for command execution
BASH_DEFAULT_TIMEOUT_MS = 120000  # 2 minutes
BASH_MAX_TIMEOUT_MS = 600000  # 10 minutes


@dataclass(frozen=True)
class ExecutionMetadata:
    """Metadata about command execution."""

    duration_ms: int


@runtime_checkable
class Computer(Protocol):
    """Protocol for Computer implementations.

    A Computer runs CLI commands. Each command is transient - no state persists.
    """

    @property
    def is_running(self) -> bool:
        """Check if the computer is running."""
        ...

    async def start(self) -> None:
        """Start the computer. Idempotent."""
        ...

    async def run(self, command: str, *, timeout: float | None = None) -> CLIResult:  # noqa: ASYNC109
        """Execute a command. Auto-starts if needed."""
        ...

    async def stop(self) -> None:
        """Stop the computer. Idempotent."""
        ...


class AsyncComputerMixin:
    """Mixin for async context manager support via start()/stop()."""

    async def __aenter__(self) -> Self:
        """Enter async context by starting the computer."""
        await self.start()  # type: ignore[attr-defined]
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit async context by stopping the computer."""
        await self.stop()  # type: ignore[attr-defined]
