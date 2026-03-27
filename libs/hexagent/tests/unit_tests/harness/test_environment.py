# ruff: noqa: PLR2004
"""Tests for EnvironmentResolver."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from hexagent.harness.environment import EnvironmentResolver
from hexagent.types import CLIResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DELIM = "___ENV___"


def _make_stdout(
    *,
    cwd: str = "/home/user",
    git: str = "true",
    platform: str = "linux",
    shell: str = "bash",
    os_version: str = "Linux 6.1.0",
    date: str = "2026-03-13T10:30:00-0800",
) -> str:
    return f"{cwd}\n{_DELIM}\n{git}\n{_DELIM}\n{platform}\n{_DELIM}\n{shell}\n{_DELIM}\n{os_version}\n{_DELIM}\n{date}"


def _mock_computer(stdout: str) -> AsyncMock:
    computer = AsyncMock()
    computer.run = AsyncMock(return_value=CLIResult(stdout=stdout, stderr="", exit_code=0))
    return computer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestResolve:
    """Tests for EnvironmentResolver.resolve()."""

    async def test_parses_all_fields(self) -> None:
        computer = _mock_computer(_make_stdout())
        env = await EnvironmentResolver(computer).resolve()

        assert env.working_dir == "/home/user"
        assert env.is_git_repo is True
        assert env.platform == "linux"
        assert env.shell == "bash"
        assert env.os_version == "Linux 6.1.0"
        assert env.today_date.year == 2026
        assert env.today_date.month == 3

    async def test_git_repo_false(self) -> None:
        computer = _mock_computer(_make_stdout(git="false"))
        env = await EnvironmentResolver(computer).resolve()

        assert env.is_git_repo is False

    async def test_git_repo_case_insensitive(self) -> None:
        computer = _mock_computer(_make_stdout(git="True"))
        env = await EnvironmentResolver(computer).resolve()

        assert env.is_git_repo is True

    async def test_datetime_with_timezone(self) -> None:
        computer = _mock_computer(_make_stdout(date="2026-03-13T10:30:00+0000"))
        env = await EnvironmentResolver(computer).resolve()

        assert env.today_date.tzinfo is not None
        assert env.today_date == datetime(2026, 3, 13, 10, 30, 0, tzinfo=UTC)

    async def test_datetime_without_timezone_fallback(self) -> None:
        """Falls back to naive datetime when timezone offset is missing."""
        computer = _mock_computer(_make_stdout(date="2026-03-13T10:30:00"))
        env = await EnvironmentResolver(computer).resolve()

        assert env.today_date.year == 2026
        assert env.today_date.tzinfo is None

    async def test_empty_datetime_fallback_now(self) -> None:
        computer = _mock_computer(_make_stdout(date=""))
        env = await EnvironmentResolver(computer).resolve()
        assert isinstance(env.today_date, datetime)

    async def test_pads_missing_parts(self) -> None:
        """When stdout has fewer delimiters, missing fields are padded."""
        # Only cwd and git — missing platform, shell, os_version, date
        stdout = f"/home/user\n{_DELIM}\ntrue"
        computer = _mock_computer(stdout)

        # Date will be empty -> fallback to current time.
        env = await EnvironmentResolver(computer).resolve()
        assert isinstance(env.today_date, datetime)

    async def test_darwin_platform(self) -> None:
        computer = _mock_computer(_make_stdout(platform="darwin", os_version="Darwin 25.3.0"))
        env = await EnvironmentResolver(computer).resolve()

        assert env.platform == "darwin"
        assert env.os_version == "Darwin 25.3.0"

    async def test_delegates_to_computer_run(self) -> None:
        """Verifies the resolver calls computer.run with a command."""
        computer = _mock_computer(_make_stdout())
        await EnvironmentResolver(computer).resolve()

        computer.run.assert_awaited_once()
        cmd = computer.run.call_args.args[0]
        assert _DELIM in cmd
        assert "pwd" in cmd
        assert "uname" in cmd
