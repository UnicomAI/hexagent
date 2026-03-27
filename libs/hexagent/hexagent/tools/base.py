"""Base classes for agent tools.

This module defines the abstract interface for agent tools.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from hexagent.types import ToolResult

ParamsT = TypeVar("ParamsT", bound=BaseModel)


def _format_validation_errors(
    error: ValidationError,
    tool_name: str | None = None,
) -> str:
    """Format pydantic validation errors into an LLM-friendly message."""
    lines = [f"Tool call{f' to `{tool_name}`' if tool_name else ''} failed due to {error.error_count()} invalid parameter(s):"]

    for err in error.errors(include_url=False):
        loc = " -> ".join(str(s) for s in err.get("loc", [])) or "<root>"
        lines.append(f"- `{loc}`: {err['msg']} (type={err['type']}, input={err.get('input')!r})")

    return "\n".join(lines)


class BaseAgentTool(ABC, Generic[ParamsT]):
    """Abstract base class for agent tools.

    Provides a consistent interface for tools that can be used by AI agents.
    Subclasses must define:
    - name: str - Tool identifier
    - description: str - Tool description for LLM
    - args_schema: type[ParamsT] - Pydantic model for input validation

    The base class provides:
    - __call__: Validates inputs via args_schema and calls execute()
    - json_schema: Property returning the JSON schema for inputs

    Examples:
        Creating a custom tool:
        ```python
        class MyToolParams(BaseModel):
            arg1: str = Field(description="First argument")


        class MyTool(BaseAgentTool[MyToolParams]):
            name: str = "MyTool"
            description: str = "Does something useful"
            args_schema = MyToolParams

            async def execute(self, params: MyToolParams) -> ToolResult:
                return ToolResult(output=f"Processed: {params.arg1}")
        ```
    """

    name: str
    description: str = ""
    instruction: str = ""
    args_schema: type[ParamsT]

    @property
    def json_schema(self) -> dict[str, Any]:
        """JSON schema for tool inputs."""
        return self.args_schema.model_json_schema()

    async def __call__(self, **kwargs: Any) -> ToolResult:
        """Execute tool with automatic input validation.

        Args:
            **kwargs: Tool-specific arguments matching args_schema.

        Returns:
            ToolResult containing the output of the tool execution.

        Raises:
            ToolError: For recoverable errors that the agent can handle.
        """
        try:
            params = self.args_schema(**kwargs)
        except ValidationError as e:
            err_msg = f"<tool_call_error>{_format_validation_errors(e, self.name)}</tool_call_error>"
            return ToolResult(error=err_msg)

        return await self.execute(params)

    @abstractmethod
    async def execute(self, params: ParamsT) -> ToolResult:
        """Execute the tool with validated params.

        Args:
            params: Validated parameters matching args_schema.

        Returns:
            ToolResult containing the output of the tool execution.

        Raises:
            ToolError: For recoverable errors that the agent can handle.
        """
        ...
