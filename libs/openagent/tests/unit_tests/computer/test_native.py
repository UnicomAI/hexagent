"""Tests for LocalNativeComputer."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from openagent.computer import Computer, LocalNativeComputer
from openagent.computer.base import BASH_MAX_TIMEOUT_MS
from openagent.exceptions import CLIError, UnsupportedPlatformError

# Test constants
_NONZERO_EXIT_CODE = 42
_SHORT_TIMEOUT_MS = 500.0
_OVER_MAX_TIMEOUT_MS = BASH_MAX_TIMEOUT_MS + 100000
_MIN_DURATION_MS = 50  # Minimum expected duration for sleep 0.1


class TestInit:
    """Tests for __init__."""

    def test_rejects_windows_platform(self) -> None:
        """Test UnsupportedPlatformError is raised on Windows."""
        with (
            patch.object(sys, "platform", "win32"),
            pytest.raises(UnsupportedPlatformError, match="Unix-like"),
        ):
            LocalNativeComputer()

    def test_accepts_unix_platforms(self) -> None:
        """Test Unix-like platforms are accepted."""
        for platform in ("linux", "darwin", "freebsd"):
            with patch.object(sys, "platform", platform):
                computer = LocalNativeComputer()
                assert computer is not None


class TestProperties:
    """Tests for properties."""

    def test_is_running_always_true(self) -> None:
        """Test is_running always returns True for transient design."""
        computer = LocalNativeComputer()
        assert computer.is_running is True

    async def test_is_running_remains_true_after_operations(self) -> None:
        """Test is_running stays True after run and stop."""
        computer = LocalNativeComputer()
        assert computer.is_running is True

        await computer.run("echo hello")
        assert computer.is_running is True

        await computer.stop()
        # Still True - stop() is a no-op for transient design
        assert computer.is_running is True


class TestStartStop:
    """Tests for start() and stop()."""

    async def test_start_is_noop(self) -> None:
        """Test start() does nothing."""
        computer = LocalNativeComputer()
        await computer.start()
        # No state change expected

    async def test_stop_is_noop(self) -> None:
        """Test stop() does nothing."""
        computer = LocalNativeComputer()
        await computer.stop()
        # No state change expected

    async def test_idempotent_start_stop(self) -> None:
        """Test start() and stop() are idempotent no-ops."""
        computer = LocalNativeComputer()
        await computer.start()
        await computer.start()  # No error
        await computer.stop()
        await computer.stop()  # No error


class TestRun:
    """Tests for run()."""

    async def test_basic_execution(self) -> None:
        """Test simple command returns correct output."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("echo hello")
            assert result.stdout == "hello"
            assert result.exit_code == 0

    async def test_stderr_captured(self) -> None:
        """Test stderr is captured separately."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("echo error >&2")
            assert result.stderr == "error"
            assert result.exit_code == 0

    async def test_combined_stdout_stderr(self) -> None:
        """Test both stdout and stderr are captured."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("echo out && echo err >&2")
            assert result.stdout == "out"
            assert result.stderr == "err"
            assert result.exit_code == 0

    async def test_empty_output(self) -> None:
        """Test command with no output."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("true")
            assert result.stdout == ""
            assert result.stderr == ""
            assert result.exit_code == 0

    async def test_multiline_output(self) -> None:
        """Test multiline output is captured correctly."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("echo 'line1\nline2\nline3'")
            assert "line1" in result.stdout
            assert "line2" in result.stdout
            assert "line3" in result.stdout

    async def test_nonzero_exit_code(self) -> None:
        """Test non-zero exit codes are returned, not raised."""
        async with LocalNativeComputer() as computer:
            result = await computer.run(f"exit {_NONZERO_EXIT_CODE}")
            assert result.exit_code == _NONZERO_EXIT_CODE

    async def test_command_not_found(self) -> None:
        """Test command not found returns non-zero exit code."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("command_that_does_not_exist_12345")
            assert result.exit_code != 0
            assert result.stderr != ""

    async def test_special_characters_in_output(self) -> None:
        """Test special characters are handled correctly."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("echo 'hello $USER \"quoted\"'")
            assert "hello" in result.stdout
            assert result.exit_code == 0

    async def test_unicode_output(self) -> None:
        """Test unicode characters are handled correctly."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("echo '你好世界 🌍'")
            assert "你好世界" in result.stdout
            assert result.exit_code == 0

    async def test_single_trailing_newline_stripped(self) -> None:
        """Test only a single trailing newline is stripped (removesuffix)."""
        async with LocalNativeComputer() as computer:
            # echo appends one \n — removesuffix removes exactly that one
            result = await computer.run("echo hello")
            assert result.stdout == "hello"

    async def test_multiple_trailing_newlines_preserve_inner(self) -> None:
        """Test removesuffix only strips the last newline, preserving others."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("printf 'hello\\n\\n'")
            # removesuffix("\n") strips one trailing \n, leaving "hello\n"
            assert result.stdout == "hello\n"


class TestTimeout:
    """Tests for timeout handling."""

    async def test_timeout_raises_cli_error(self) -> None:
        """Test timeout raises CLIError."""
        async with LocalNativeComputer() as computer:
            with pytest.raises(CLIError, match="timed out"):
                await computer.run("sleep 10", timeout=_SHORT_TIMEOUT_MS)

    async def test_timeout_in_milliseconds(self) -> None:
        """Test timeout is interpreted as milliseconds."""
        async with LocalNativeComputer() as computer:
            # 100ms timeout should fail for sleep 1
            with pytest.raises(CLIError, match="timed out"):
                await computer.run("sleep 1", timeout=100.0)

    async def test_uses_default_timeout(self) -> None:
        """Test default timeout is used when not specified."""
        async with LocalNativeComputer() as computer:
            # Quick command should succeed with default timeout
            result = await computer.run("echo hello")
            assert result.exit_code == 0

    async def test_timeout_capped_at_max(self) -> None:
        """Test timeout is capped at BASH_MAX_TIMEOUT_MS."""
        async with LocalNativeComputer() as computer:
            # Even with a huge timeout, should work for quick command
            result = await computer.run("echo hello", timeout=_OVER_MAX_TIMEOUT_MS)
            assert result.exit_code == 0

    async def test_process_killed_on_timeout(self) -> None:
        """Test process is killed when timeout occurs."""
        async with LocalNativeComputer() as computer:
            # This should timeout and the process should be killed
            with pytest.raises(CLIError, match="timed out"):
                # Use a command that would run indefinitely
                await computer.run("sleep 100", timeout=100.0)
            # If we got here without hanging, the process was killed


class TestMetadata:
    """Tests for execution metadata."""

    async def test_metadata_has_duration(self) -> None:
        """Test execution metadata includes duration."""
        async with LocalNativeComputer() as computer:
            result = await computer.run("echo hello")
            assert result.metadata is not None
            assert result.metadata.duration_ms >= 0

    async def test_duration_reflects_execution_time(self) -> None:
        """Test duration roughly reflects actual execution time."""
        async with LocalNativeComputer() as computer:
            # Run a command that takes measurable time
            result = await computer.run("sleep 0.1")
            assert result.metadata is not None
            # Should be at least 100ms (with tolerance for scheduling)
            assert result.metadata.duration_ms >= _MIN_DURATION_MS


class TestContextManager:
    """Tests for async context manager support."""

    async def test_context_manager_works(self) -> None:
        """Test async with works (start/stop are no-ops)."""
        computer = LocalNativeComputer()
        async with computer:
            result = await computer.run("echo hello")
            assert result.stdout == "hello"

    async def test_context_manager_can_be_reused(self) -> None:
        """Test context manager can be entered multiple times."""
        computer = LocalNativeComputer()

        async with computer:
            result1 = await computer.run("echo first")
            assert result1.stdout == "first"

        async with computer:
            result2 = await computer.run("echo second")
            assert result2.stdout == "second"


class TestProtocolCompliance:
    """Tests for Computer protocol compliance."""

    def test_satisfies_computer_protocol(self) -> None:
        """Test LocalNativeComputer satisfies Computer protocol."""
        computer = LocalNativeComputer()
        assert isinstance(computer, Computer)

    def test_has_required_methods(self) -> None:
        """Test all required protocol methods exist."""
        computer = LocalNativeComputer()
        assert hasattr(computer, "is_running")
        assert hasattr(computer, "start")
        assert hasattr(computer, "run")
        assert hasattr(computer, "stop")
        assert callable(computer.start)
        assert callable(computer.run)
        assert callable(computer.stop)
