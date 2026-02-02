"""Exceptions for OpenAgent.

This module defines exceptions raised by OpenAgent tools and components.
"""


class ConfigurationError(Exception):
    """Exception raised when required configuration is missing or invalid.

    Raise ConfigurationError when:
    - Required environment variables are missing (API keys, credentials)
    - Configuration values are invalid or malformed

    Examples:
        ```python
        if "API_KEY" not in os.environ:
            msg = "API_KEY environment variable not set. Get your API key at example.com"
            raise ConfigurationError(msg)
        ```
    """


class UnsupportedPlatformError(Exception):
    """Exception raised when the platform doesn't meet requirements.

    Raise UnsupportedPlatformError when:
    - Operating system is not supported (e.g., Windows vs Unix)
    - Architecture is not supported
    - Required system capabilities are missing

    Examples:
        ```python
        if sys.platform == "win32":
            msg = "Requires Unix-like system (Linux, macOS)"
            raise UnsupportedPlatformError(msg)
        ```
    """


class MissingDependencyError(Exception):
    """Exception raised when an optional dependency is not installed.

    Raise MissingDependencyError when:
    - An optional package is required but not installed
    - A feature requires additional dependencies

    Examples:
        ```python
        try:
            import e2b
        except ImportError as e:
            msg = "E2B package not installed. Install with: pip install e2b"
            raise MissingDependencyError(msg) from e
        ```
    """


class ToolError(Exception):
    """Exception raised when a tool cannot execute the requested operation.

    This exception indicates infrastructure-level failures where the command
    could not be executed at all. It should NOT be used for command failures
    (non-zero exit codes) - those are returned in ToolResult/CLIResult.

    Raise ToolError when:
    - Tool infrastructure fails (shell not available, permission denied)
    - Session state is invalid (not started, timed out, process died)
    - Timeout waiting for command completion
    - Invalid input (empty command, blocked command)
    - Unexpected internal errors (sanitized to hide implementation details)

    Do NOT raise ToolError when:
    - Command executed but returned non-zero exit code
    - Command produced stderr output
    - Command returned "command not found" (exit 127)

    The agent receives this error and can decide how to proceed (e.g., restart).

    Examples:
        ```python
        try:
            result = await session.run("sleep 1000")
        except ToolError as e:
            # Session timed out - agent can restart and retry
            result = await tool(restart=True)
            result = await tool(command="echo hello")
        ```
    """


class ExternalServiceError(Exception):
    """External service call failed.

    Base exception for all external service failures. Use this to catch
    any external service error regardless of the specific service type.

    Subclasses:
        WebAPIError: Web API calls (fetch, search providers)
    """


class WebAPIError(ExternalServiceError):
    """Web API call failed.

    Raised when a web provider (fetch or search) cannot complete
    the request due to API errors, invalid responses, or service issues.

    Examples:
        ```python
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise WebAPIError(f"Firecrawl: {e}") from e
        ```
    """


class CLIError(Exception):
    """Error raised when the computer has an infrastructure failure.

    This exception indicates that the CLI computer itself encountered an error,
    NOT that a command returned a non-zero exit code.

    Use CLIError for:
    - Computer failed to start
    - Process died unexpectedly
    - Command timed out
    - Internal errors in the computer implementation

    Do NOT use CLIError for:
    - Command returned non-zero exit code (use CLIResult.exit_code)
    - Command wrote to stderr (use CLIResult.stderr)
    - Command not found (exit code 127 in CLIResult)

    Examples:
        ```python
        # Computer failed to start
        raise CLIError("Failed to start bash process: permission denied")

        # Command timed out
        raise CLIError("Command timed out after 120 seconds; computer must be restarted")

        # Process died
        raise CLIError("bash has exited with returncode -9 and must be restarted")
        ```
    """


CLI_INFRA_ERROR_SYSTEM_REMINDER = (
    "The execution environment has failed unexpectedly. This is an"
    " unrecoverable system-level failure, not a tool error. Stop current"
    " work and report this error to the user."
)
