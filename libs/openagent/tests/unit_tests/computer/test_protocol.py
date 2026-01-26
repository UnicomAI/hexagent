"""Test Computer protocol with mocks."""

from openagent.computer import Computer
from openagent.types import CLIResult


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
            timeout: float | None = None,  # noqa: ASYNC109, ARG002
        ) -> CLIResult:
            return CLIResult(stdout=f"mocked: {command}")

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
            timeout: float | None = None,  # noqa: ASYNC109, ARG002
        ) -> CLIResult:
            return CLIResult(stdout=f"ran: {command}", exit_code=0)

        async def restart(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    mock = MockComputer()
    result = await mock.run("echo test")
    assert result.stdout == "ran: echo test"
    assert result.exit_code == 0
