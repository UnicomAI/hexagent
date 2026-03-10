"""Base classes for Computer abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Self, runtime_checkable

if TYPE_CHECKING:
    from openagent.types import CLIResult

# Safety cap for command execution timeout
BASH_MAX_TIMEOUT_MS = 600000  # 10 minutes

# Standard session directories (relative to $HOME).
SESSION_TMP_DIR = "tmp"
SESSION_MNT_DIR = "mnt"
SESSION_OUTPUTS_DIR = "mnt/outputs"
SESSION_UPLOADS_DIR = "mnt/uploads"
SESSION_SKILLS_DIR = "mnt/.skills"

SESSION_DIRS: tuple[str, ...] = (
    SESSION_TMP_DIR,
    SESSION_MNT_DIR,
    SESSION_OUTPUTS_DIR,
    SESSION_UPLOADS_DIR,
    SESSION_SKILLS_DIR,
)


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

    async def upload(self, src: str, dst: str) -> None:
        """Transfer a file from the host to the computer.

        Args:
            src: Absolute path on the host filesystem.
            dst: Absolute path on the computer filesystem.

        Raises:
            FileNotFoundError: If src does not exist on the host.
            CLIError: If the transfer fails.
        """
        ...

    async def download(self, src: str, dst: str) -> None:
        """Transfer a file from the computer to the host.

        Args:
            src: Absolute path on the computer filesystem.
            dst: Absolute path on the host filesystem.

        Raises:
            CLIError: If the transfer fails.
        """
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
