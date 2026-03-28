"""Test Computer protocol and base types."""

import pytest

from clawwork.computer import Computer
from clawwork.computer.base import Mount
from clawwork.types import CLIResult


def test_mock_satisfies_protocol() -> None:
    """Test that a simple mock satisfies Computer protocol."""

    class MockComputer:
        @property
        def is_running(self) -> bool:
            return True

        async def start(self) -> None:
            pass

        async def run(
            self,
            command: str,
            *,
            timeout: float | None = None,
        ) -> CLIResult:
            return CLIResult(stdout=f"mocked: {command}")

        async def upload(self, src: str, dst: str) -> None:
            pass

        async def download(self, src: str, dst: str) -> None:
            pass

        async def restart(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    mock = MockComputer()
    assert isinstance(mock, Computer)


async def test_mock_can_execute() -> None:
    """Test mock can be used like real computer."""

    class MockComputer:
        @property
        def is_running(self) -> bool:
            return True

        async def start(self) -> None:
            pass

        async def run(
            self,
            command: str,
            *,
            timeout: float | None = None,
        ) -> CLIResult:
            return CLIResult(stdout=f"ran: {command}", exit_code=0)

        async def upload(self, src: str, dst: str) -> None:
            pass

        async def download(self, src: str, dst: str) -> None:
            pass

        async def restart(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    mock = MockComputer()
    result = await mock.run("echo test")
    assert result.stdout == "ran: echo test"
    assert result.exit_code == 0


class TestMountValidation:
    """Tests for Mount.__post_init__ validation."""

    def test_empty_target_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            Mount(source="/host/dir", target="")

    def test_relative_with_dotdot_raises(self) -> None:
        with pytest.raises(ValueError, match="must not contain"):
            Mount(source="/host/dir", target="foo/../bar")

    def test_dotdot_only_raises(self) -> None:
        with pytest.raises(ValueError, match="must not contain"):
            Mount(source="/host/dir", target="..")

    def test_absolute_with_dotdot_allowed(self) -> None:
        """Absolute paths bypass the traversal check."""
        m = Mount(source="/host/dir", target="/foo/../bar")
        assert m.target == "/foo/../bar"

    def test_valid_relative_target(self) -> None:
        m = Mount(source="/host/dir", target="project")
        assert m.target == "project"

    def test_valid_absolute_target(self) -> None:
        m = Mount(source="/host/dir", target="/opt/tools")
        assert m.target == "/opt/tools"

    def test_nested_relative_target(self) -> None:
        m = Mount(source="/host/dir", target=".skills/coding")
        assert m.target == ".skills/coding"
