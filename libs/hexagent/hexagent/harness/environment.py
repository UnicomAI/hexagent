"""Environment detection for system prompt assembly.

EnvironmentResolver runs lightweight shell commands against a Computer
to populate an ``EnvironmentContext`` used by prompt section functions.
"""

from __future__ import annotations

import logging
import shlex
from datetime import datetime
from typing import TYPE_CHECKING

from hexagent.types import EnvironmentContext

if TYPE_CHECKING:
    from hexagent.computer.base import Computer

logger = logging.getLogger(__name__)


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

    async def _probe_datetime(self) -> datetime:
        """Best-effort datetime probe that never raises.

        Returns:
            Timezone-aware datetime when possible; falls back to UTC now.
        """
        # Primary probe: timezone-aware ISO-8601 from shell date.
        probe = await self._computer.run("date '+%Y-%m-%dT%H:%M:%S%z'")
        raw = (probe.stdout or "").strip()
        if raw:
            try:
                return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                try:
                    return datetime.strptime(raw[:19], "%Y-%m-%dT%H:%M:%S")  # noqa: DTZ007
                except ValueError:
                    logger.warning("Unparseable environment datetime probe: %r", raw)

        # Secondary probe: Python inside guest (if available).
        py_probe = await self._computer.run(
            "python3 -c \"from datetime import datetime as d; print(d.now().astimezone().strftime('%Y-%m-%dT%H:%M:%S%z'))\""
        )
        py_raw = (py_probe.stdout or "").strip()
        if py_raw:
            try:
                return datetime.strptime(py_raw, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                try:
                    return datetime.strptime(py_raw[:19], "%Y-%m-%dT%H:%M:%S")  # noqa: DTZ007
                except ValueError:
                    logger.warning("Unparseable python datetime probe: %r", py_raw)

        logger.warning(
            "Environment datetime probes failed; falling back to UTC now. date.stdout=%r date.stderr=%r python3.stdout=%r python3.stderr=%r",
            probe.stdout,
            probe.stderr,
            py_probe.stdout,
            py_probe.stderr,
        )
        return datetime.now().astimezone()

    async def resolve(self) -> EnvironmentContext:
        """Detect environment properties from the computer.

        Returns:
            An ``EnvironmentContext`` snapshot.
        """
        # Single batched command: 6 values separated by a unique delimiter.
        delimiter = "___ENV___"
        qd = shlex.quote(delimiter)
        cmd = (
            "pwd; "
            f"printf '%s\\n' {qd}; "
            "(git rev-parse --is-inside-work-tree 2>/dev/null || echo false); "
            f"printf '%s\\n' {qd}; "
            "uname -s | tr '[:upper:]' '[:lower:]'; "
            f"printf '%s\\n' {qd}; "
            'basename "${SHELL:-bash}"; '
            f"printf '%s\\n' {qd}; "
            "uname -sr; "
            f"printf '%s\\n' {qd}; "
            "date '+%Y-%m-%dT%H:%M:%S%z'"
        )
        result = await self._computer.run(cmd)
        parts = result.stdout.strip().split(delimiter)

        # Pad to expected length so index access is always safe.
        _EXPECTED_PARTS = 6  # noqa: N806
        values = [p.strip() for p in parts]
        while len(values) < _EXPECTED_PARTS:
            values.append("")

        # Parse into a datetime. Shell usually outputs timezone-aware ISO 8601,
        # e.g. "2026-02-14T10:30:00-0800". If missing, probe separately.
        raw_dt = values[5]
        if raw_dt:
            try:
                now = datetime.strptime(raw_dt, "%Y-%m-%dT%H:%M:%S%z")
            except ValueError:
                now = datetime.strptime(raw_dt[:19], "%Y-%m-%dT%H:%M:%S")  # noqa: DTZ007
        else:
            logger.warning(
                "Environment shell returned empty datetime; falling back probe. stdout=%r stderr=%r exit=%s",
                result.stdout,
                result.stderr,
                result.exit_code,
            )
            now = await self._probe_datetime()

        return EnvironmentContext(
            working_dir=values[0],
            is_git_repo=values[1].strip().lower() == "true",
            platform=values[2],
            shell=values[3],
            os_version=values[4],
            today_date=now,
        )
