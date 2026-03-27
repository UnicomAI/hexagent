"""Environment detection for system prompt assembly.

EnvironmentResolver runs lightweight shell commands against a Computer
to populate the ``${…}`` placeholders in ``system_prompt_environment.md``.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from hexagent.types import EnvironmentContext

if TYPE_CHECKING:
    from hexagent.computer.base import Computer


class EnvironmentResolver:
    """Detects runtime environment properties via a Computer.

    Runs a single batched shell command to collect platform, shell,
    OS version, working directory, and git status — avoiding multiple
    round-trips with remote computers.

    Examples:
        ```python
        resolver = EnvironmentResolver(computer)
        env = await resolver.resolve()
        # env == EnvironmentContext(working_dir="/home/user", platform="linux", ...)
        ```
    """

    def __init__(self, computer: Computer) -> None:
        """Initialize the resolver.

        Args:
            computer: The Computer instance for running detection commands.
        """
        self._computer = computer

    async def resolve(self) -> EnvironmentContext:
        """Detect environment properties from the computer.

        Returns:
            An ``EnvironmentContext`` snapshot.
        """
        # Single batched command: 6 values separated by a unique delimiter.
        delimiter = "___ENV___"
        cmd = (
            f'printf "%s\\n" '
            f'"$(pwd)" '
            f'"{delimiter}" '
            f'"$(git rev-parse --is-inside-work-tree 2>/dev/null || echo false)" '
            f'"{delimiter}" '
            f'"$(uname -s | tr "[:upper:]" "[:lower:]")" '
            f'"{delimiter}" '
            f'"$(basename "$SHELL")" '
            f'"{delimiter}" '
            f'"$(uname -sr)" '
            f'"{delimiter}" '
            f"\"$(date '+%Y-%m-%dT%H:%M:%S%z')\""
        )
        result = await self._computer.run(cmd)
        parts = result.stdout.strip().split(delimiter)

        # Pad to expected length so index access is always safe.
        _EXPECTED_PARTS = 6  # noqa: N806
        values = [p.strip() for p in parts]
        while len(values) < _EXPECTED_PARTS:
            values.append("")

        # Parse into a timezone-aware datetime.
        # Shell outputs ISO 8601 with numeric offset, e.g. "2026-02-14T10:30:00-0800".
        raw_dt = values[5]
        if raw_dt:
            try:
                now = datetime.strptime(raw_dt, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                now = datetime.strptime(raw_dt[:19], "%Y-%m-%dT%H:%M:%S")  # noqa: DTZ007
        else:
            # Some hosts occasionally return empty stdout for this probe.
            # Degrade gracefully so environment detection does not block task execution.
            now = datetime.now().astimezone()

        return EnvironmentContext(
            working_dir=values[0],
            is_git_repo=values[1].strip().lower() == "true",
            platform=values[2],
            shell=values[3],
            os_version=values[4],
            today_date=now,
        )
