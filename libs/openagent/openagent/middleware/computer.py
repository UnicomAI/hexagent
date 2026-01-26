"""Computer Middleware for providing computer tools to an agent.

This middleware provides agents with a Computer - the core abstraction
that gives agents CLI-based computer access through bash and file tools.

Tools provided:
- bash: Execute arbitrary bash commands
- read: Read file contents with line numbers
- write: Create or overwrite files
- edit: Perform string replacements in files
- ls: List directory contents
- glob: Find files by pattern
- grep: Search for patterns in files
"""

from collections.abc import Awaitable, Callable, Sequence

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain_core.tools import BaseTool

from openagent.computer import Computer
from openagent.tools import create_computer_tools
from openagent.tools.adapter import to_langchain_tool

COMPUTER_SYSTEM_PROMPT = """## Computer Tools

You have access to tools for interacting with the computer (filesystem and shell):

- **bash**: Execute shell commands (state persists across calls)
- **read**: Read file contents with line numbers
- **write**: Create or overwrite files
- **edit**: Perform string replacements in files
- **ls**: List directory contents
- **glob**: Find files by pattern
- **grep**: Search file contents

All file paths should be absolute (starting with /).
The bash session maintains working directory, environment variables, and shell functions across commands."""


class ComputerMiddleware(AgentMiddleware):
    """Middleware providing computer tools to an agent.

    This middleware creates a Computer and provides tools that use it,
    giving agents the ability to interact with a computer via shell and files.

    Tools provided:
    - bash: Execute arbitrary bash commands
    - read: Read file contents with line numbers
    - write: Create or overwrite files
    - edit: Perform string replacements in files
    - ls: List directory contents
    - glob: Find files by pattern
    - grep: Search for patterns in files

    All tools share the same Computer, so state (cwd, env vars, etc.)
    persists across tool calls.

    Args:
        computer: The Computer instance to use for CLI tools.
        system_prompt: Optional custom system prompt override.

    Example:
        ```python
        from openagent.middleware.computer import ComputerMiddleware
        from openagent.computer import LocalNativeComputer

        middleware = ComputerMiddleware(computer=LocalNativeComputer())
        ```
    """

    def __init__(
        self,
        computer: Computer,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize the ComputerMiddleware.

        Args:
            computer: The Computer instance to use for CLI tools.
            system_prompt: Optional custom system prompt override.
        """
        self._computer = computer
        self._custom_system_prompt = system_prompt
        # Lazily create tools on first access
        self._tools_cache: list[BaseTool] | None = None

    @property
    def tools(self) -> Sequence[BaseTool]:  # type: ignore[override]
        """Get the computer tools as LangChain tools.

        Tools are created lazily and cached.
        """
        if self._tools_cache is None:
            self._tools_cache = self._create_langchain_tools()
        return self._tools_cache

    def _create_langchain_tools(self) -> list[BaseTool]:
        """Create LangChain tools from the Computer.

        Uses create_computer_tools() to create all agent tools, then converts
        them to LangChain format. Descriptions and schemas are derived from
        the OpenAgent tools themselves.

        Returns:
            List of LangChain BaseTool instances.
        """
        agent_tools = create_computer_tools(self._computer)
        return [to_langchain_tool(tool) for tool in agent_tools]

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject computer tools system prompt into the model request.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        system_prompt = self._custom_system_prompt or COMPUTER_SYSTEM_PROMPT

        if system_prompt:
            updated_prompt = request.system_prompt + "\n\n" + system_prompt if request.system_prompt else system_prompt
            request = request.override(system_prompt=updated_prompt)  # type: ignore[call-arg]

        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """(async) Inject computer tools system prompt into the model request.

        Args:
            request: The model request being processed.
            handler: The handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        system_prompt = self._custom_system_prompt or COMPUTER_SYSTEM_PROMPT

        if system_prompt:
            updated_prompt = request.system_prompt + "\n\n" + system_prompt if request.system_prompt else system_prompt
            request = request.override(system_prompt=updated_prompt)  # type: ignore[call-arg]

        return await handler(request)
