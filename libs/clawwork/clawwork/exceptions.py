"""Exceptions for ClawWork.

This module defines exceptions raised by ClawWork tools and components.
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


class VMMountConflictError(ValueError):
    """Raised when a VM mount's guest path conflicts with an existing mount.

    This is a user-correctable error — the caller should choose a different
    target path or remove the conflicting mount first.

    Examples:
        ```python
        raise VMMountConflictError("Mount conflict: guest path '/mnt/code' is already in use")
        ```
    """


class VMError(Exception):
    """Base error for VM infrastructure failures.

    This exception indicates that a VM backend (Lima, WSL, etc.) encountered
    an error — creating, starting, stopping, or executing shell commands.

    Raise VMError (or a subclass) when:
    - VM failed to create or start
    - VM did not reach Running state within timeout
    - Shell command on the VM timed out
    - Session user creation or validation failed
    - Any VM infrastructure operation fails

    Do NOT raise VMError when:
    - A command inside Computer.run() fails (use CLIError)
    - A shell command returns non-zero exit code (use CLIResult.exit_code)
    - Platform or dependency checks fail (use UnsupportedPlatformError / MissingDependencyError)
    """


class LimaError(VMError):
    """Error raised when Lima VM infrastructure fails.

    Examples:
        ```python
        # VM did not start
        raise LimaError("Lima instance 'clawwork' did not reach Running state within 120s")

        # Shell command timed out
        raise LimaError("timed out after 30s")

        # Session user not found
        raise LimaError("Session user 'foo' does not exist on the VM")
        ```
    """


class WslError(VMError):
    """Error raised when WSL VM infrastructure fails.

    Examples:
        ```python
        # Distro did not start
        raise WslError("WSL distro 'clawwork' did not start within 60s")

        # WSL not installed
        raise WslError("wsl.exe not found — WSL2 must be installed")

        # Shell command timed out
        raise WslError("timed out after 30s")
        ```
    """


class SkillError(Exception):
    """Base error for skill-related failures.

    Use this to catch any skill error regardless of the specific cause.

    Subclasses:
        SkillParseError: Structural problems in SKILL.md.
        SkillValidationError: Field values violate the Agent Skills spec.
    """


class SkillParseError(SkillError):
    """SKILL.md file cannot be structurally parsed.

    Raised when a SKILL.md file has structural problems that prevent
    extracting a valid skill specification.

    Raise SkillParseError when:
    - Missing or malformed frontmatter delimiters (``---``)
    - YAML in the frontmatter block is syntactically invalid
    - Required fields (``name``, ``description``) are absent

    Do NOT raise SkillParseError when:
    - Field values are present but violate constraints (use SkillValidationError)
    - The skill directory structure is wrong (that's a resolver concern)

    Examples:
        ```python
        raise SkillParseError("SKILL.md must start with '---' frontmatter delimiter")

        raise SkillParseError("Invalid YAML in frontmatter: expected a mapping")
        ```
    """


class SkillValidationError(SkillError):
    """SKILL.md frontmatter values violate the Agent Skills specification.

    Raise SkillValidationError when:
    - ``name`` violates naming rules (length, character set, hyphen rules)
    - ``description`` exceeds 1024 characters or is empty
    - ``compatibility`` exceeds 500 characters
    - ``metadata`` contains non-string keys or values

    Examples:
        ```python
        raise SkillValidationError("Skill name 'PDF-Tool' is invalid: must contain only lowercase alphanumeric characters and hyphens")
        ```
    """


CLI_INFRA_ERROR_SYSTEM_REMINDER = (
    "The execution environment has failed unexpectedly. This is an"
    " unrecoverable system-level failure, not a tool error. Stop current"
    " work and report this error to the user."
)
