"""Agent middleware for wiring runtime modules to LangChain.

This middleware coordinates the runtime modules (CapabilityRegistry,
CompactionController, PermissionGate) with LangChain's agent infrastructure.

All compaction decisions are delegated to the framework-agnostic
CompactionController. This middleware translates the returned ContextUpdate
into LangChain-specific message operations.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any, Protocol

from langchain.agents.middleware.types import (
    AgentMiddleware as LangChainAgentMiddleware,
)
from langchain.agents.middleware.types import (
    AgentState,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
    hook_config,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.types import Overwrite as LangGraphOverwrite

from openagent.langchain.adapter import to_langchain_tool
from openagent.runtime import (
    CapabilityRegistry,
    CompactionController,
    CompactionPhase,
    PermissionGate,
    PermissionResult,
)
from openagent.runtime.context import (
    Append,
    ContextUpdate,
    Overwrite,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable

    from langchain_core.tools import BaseTool
    from langgraph.runtime import Runtime

# Type alias for token counter function
TokenCounter = Callable[[Sequence[BaseMessage]], int]


class ApprovalCallback(Protocol):
    """Callback for human-in-the-loop approval of tool calls.

    Implement this protocol to provide custom approval logic for
    tools that return NEEDS_APPROVAL from the permission gate.

    Examples:
        ```python
        async def cli_approval(
            tool_name: str,
            tool_args: dict[str, Any],
            approval_prompt: str | None,
        ) -> bool:
            response = input(f"Allow {tool_name}? [y/n]: ")
            return response.lower() == "y"


        middleware = AgentMiddleware(
            ...,
            approval_callback=cli_approval,
        )
        ```
    """

    async def __call__(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        approval_prompt: str | None,
    ) -> bool:
        """Request approval for a tool call.

        Args:
            tool_name: Name of the tool requesting approval.
            tool_args: Arguments passed to the tool.
            approval_prompt: Optional prompt describing why approval is needed.

        Returns:
            True if approved, False if denied.
        """
        ...


# Average characters per token (rough estimate for English text)
_CHARS_PER_TOKEN = 4

# Minimum messages required before compaction can trigger.
# A single summary message after compaction should not re-trigger.
_MIN_MESSAGES_FOR_COMPACTION = 2


def _estimate_tokens(messages: Sequence[BaseMessage]) -> int:
    """Estimate token count from messages.

    Uses a simple heuristic: ~4 characters per token for English text.

    Args:
        messages: The messages to estimate tokens for.

    Returns:
        Estimated token count.
    """
    total_chars = 0
    for msg in messages:
        content = msg.content
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, str):
                    total_chars += len(block)
                elif isinstance(block, dict) and "text" in block:
                    total_chars += len(str(block["text"]))
    return total_chars // _CHARS_PER_TOKEN


class AgentMiddleware(LangChainAgentMiddleware):
    """Middleware that wires runtime modules to LangChain agent hooks.

    Delegates compaction decisions to the framework-agnostic
    ``CompactionController`` and translates the returned ``ContextUpdate``
    into LangChain message operations.

    Coordinates:
    - CapabilityRegistry: Provides tools to the agent
    - CompactionController: 3-phase stateless compaction protocol
    - PermissionGate: Validates tool calls with optional human-in-the-loop

    Hook mapping:
    - tools property: Provides tools from CapabilityRegistry
    - abefore_model: Applies CompactionController.pre_model_update()
    - aafter_model: Applies CompactionController.post_model_transition()
    - awrap_model_call: Injects pre-assembled system prompt
    - awrap_tool_call: Validates via PermissionGate, calls approval callback

    Examples:
        Basic usage::

            middleware = AgentMiddleware(
                registry=registry,
                system_prompt="You are a helpful assistant.",
                permission_gate=PermissionGate(),
                compaction_prompt=library.get("compaction/request"),
                summary_rebuild_template=library.get("compaction/summary_rebuild"),
            )
    """

    def __init__(
        self,
        registry: CapabilityRegistry,
        system_prompt: str,
        permission_gate: PermissionGate,
        *,
        compaction_prompt: str,
        summary_rebuild_template: str,
        compaction_threshold: int = 100_000,
        count_tokens: TokenCounter | None = None,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            registry: The capability registry providing tools.
            system_prompt: The pre-assembled system prompt.
            permission_gate: The permission gate for validating tool calls.
            compaction_prompt: Prompt for requesting conversation summaries.
                Canonical source: ``compaction/request`` in PromptLibrary.
            summary_rebuild_template: Template for rebuilding context after
                compaction.  Must contain ``{summary_content}`` placeholder.
                Canonical source: ``compaction/summary_rebuild`` in PromptLibrary.
            compaction_threshold: Token count that triggers context compaction.
            count_tokens: Optional function to count tokens in messages. If not
                provided, uses character-based estimation (~4 chars/token).
            approval_callback: Optional callback for human-in-the-loop approval.
        """
        self._registry = registry
        self._system_prompt = system_prompt
        self._permission_gate = permission_gate
        self._approval_callback = approval_callback
        self._count_tokens = count_tokens or _estimate_tokens
        self._summary_rebuild_template = summary_rebuild_template

        self._compaction = CompactionController(
            compaction_prompt,
            threshold=compaction_threshold,
        )

        # Cache for converted LangChain tools
        self._tools_cache: list[BaseTool] | None = None

    @property
    def tools(self) -> Sequence[BaseTool]:  # type: ignore[override]
        """Get tools from the registry as LangChain tools.

        Returns:
            Sequence of LangChain BaseTool instances.
        """
        if self._tools_cache is None:
            self._tools_cache = [to_langchain_tool(tool) for tool in self._registry.get_tools()]
        return self._tools_cache

    # --- Async hooks (primary implementations) ---

    async def abefore_model(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Apply compaction updates before model call.

        Delegates to ``CompactionController.pre_model_update()`` and
        translates the returned ``ContextUpdate`` into LangChain message
        operations.

        Args:
            state: The current agent state containing messages.
            _runtime: The LangGraph runtime context.

        Returns:
            State updates dict, or None if no changes.
        """
        phase = CompactionPhase(state.get("compaction_phase", CompactionPhase.NONE))
        update, new_phase = self._compaction.pre_model_update(phase)

        if update is not None:
            return self._apply_context_update(state["messages"], update, new_phase)

        return None

    @hook_config(can_jump_to=["model"])
    async def aafter_model(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Check for compaction after model response.

        Delegates to ``CompactionController.post_model_transition()`` and
        returns phase transition with jump-to-model if needed.

        Args:
            state: The current agent state with messages.
            _runtime: The LangGraph runtime context.

        Returns:
            State updates dict with phase transition and jump, or None.
        """
        messages = state["messages"]
        phase = CompactionPhase(state.get("compaction_phase", CompactionPhase.NONE))

        # Need at least 2 messages to compact; a single summary message
        # after compaction should not re-trigger the cycle.
        if phase == CompactionPhase.NONE and len(messages) < _MIN_MESSAGES_FOR_COMPACTION:
            return None

        token_count = self._count_tokens(messages)
        should_rerun, new_phase = self._compaction.post_model_transition(token_count, phase)

        if should_rerun:
            return {"compaction_phase": new_phase, "jump_to": "model"}

        return None

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Inject pre-assembled system prompt before model call.

        Args:
            request: The model request being processed.
            handler: The async handler function to call with the modified request.

        Returns:
            The model response from the handler.
        """
        updated_request = request.override(system_prompt=self._system_prompt)  # type: ignore[call-arg]
        return await handler(updated_request)

    async def awrap_tool_call(  # type: ignore[override]
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage]],
    ) -> ToolMessage:
        """Check permission before tool execution.

        Args:
            request: The tool call request.
            handler: The async handler to execute the tool.

        Returns:
            The tool message response, or an error response if denied.
        """
        tool_name = request.tool_call["name"]
        tool_args = request.tool_call.get("args", {})

        decision = await self._permission_gate.check(tool_name, tool_args)

        if decision.result == PermissionResult.DENIED:
            return self._create_denied_response(request, decision.reason)

        if decision.result == PermissionResult.NEEDS_APPROVAL:
            if self._approval_callback is None:
                return self._create_denied_response(
                    request,
                    f"Action requires approval: {decision.approval_prompt or 'No details provided'}",
                )

            approved = await self._approval_callback(
                tool_name,
                tool_args,
                decision.approval_prompt,
            )

            if not approved:
                return self._create_denied_response(request, "Action denied by user")

        return await handler(request)

    # --- Private helpers ---

    def _apply_context_update(
        self,
        messages: Sequence[BaseMessage],
        update: ContextUpdate,
        new_phase: CompactionPhase,
    ) -> dict[str, Any]:
        """Translate a ContextUpdate into LangChain state updates.

        Args:
            messages: The current message history.
            update: The context update to apply.
            new_phase: The new compaction phase after this update.

        Returns:
            State updates dict with modified messages and phase.
        """
        if isinstance(update, Overwrite):
            rebuilt = self._rebuild_with_summary(messages)
            return {
                "messages": LangGraphOverwrite(rebuilt),
                "compaction_phase": new_phase,
            }

        if isinstance(update, Append):
            msgs = list(messages)
            msg_cls = HumanMessage if update.role == "user" else AIMessage
            msgs.append(msg_cls(content=update.content))
            return {"messages": msgs}

        # Inject
        msgs = list(messages)
        last = msgs[-1]
        if isinstance(last.content, str):
            content = last.content
        elif isinstance(last.content, list):
            content = "".join(block if isinstance(block, str) else block.get("text", "") for block in last.content if isinstance(block, (str, dict)))
        else:
            content = str(last.content)
        new_content = f"{update.content}\n\n{content}" if update.position == "prepend" else f"{content}\n\n{update.content}"
        kwargs: dict[str, Any] = {"content": new_content}
        if last.id is not None:
            kwargs["id"] = last.id
        if isinstance(last, ToolMessage):
            kwargs["tool_call_id"] = last.tool_call_id
        msgs[-1] = last.__class__(**kwargs)
        return {"messages": msgs}

    def _rebuild_with_summary(
        self,
        messages: Sequence[BaseMessage],
    ) -> list[BaseMessage]:
        """Extract summary from last AIMessage and rebuild message history.

        Args:
            messages: Current message history including summary response.

        Returns:
            Rebuilt message list with summary as initial context.
        """
        summary_content = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                content = msg.content
                if isinstance(content, str):
                    summary_content = content
                elif isinstance(content, list):
                    summary_content = "".join(
                        block if isinstance(block, str) else block.get("text", "") for block in content if isinstance(block, (str, dict))
                    )
                break

        return [
            HumanMessage(content=self._summary_rebuild_template.format(summary_content=summary_content)),
        ]

    def _create_denied_response(
        self,
        request: ToolCallRequest,
        reason: str | None,
    ) -> ToolMessage:
        """Create a tool response for a denied action."""
        error_message = f"Permission denied: {reason}" if reason else "Permission denied"
        return ToolMessage(
            content=error_message,
            tool_call_id=request.tool_call.get("id", ""),
        )

    # --- Sync hooks (for interface compliance) ---

    def before_model(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Sync version of abefore_model."""
        phase = CompactionPhase(state.get("compaction_phase", CompactionPhase.NONE))
        update, new_phase = self._compaction.pre_model_update(phase)

        if update is not None:
            return self._apply_context_update(state["messages"], update, new_phase)

        return None

    @hook_config(can_jump_to=["model"])
    def after_model(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Sync version of aafter_model."""
        messages = state["messages"]
        phase = CompactionPhase(state.get("compaction_phase", CompactionPhase.NONE))

        if phase == CompactionPhase.NONE and len(messages) < _MIN_MESSAGES_FOR_COMPACTION:
            return None

        token_count = self._count_tokens(messages)
        should_rerun, new_phase = self._compaction.post_model_transition(token_count, phase)

        if should_rerun:
            return {"compaction_phase": new_phase, "jump_to": "model"}

        return None

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Inject pre-assembled system prompt before model call (sync)."""
        updated_request = request.override(system_prompt=self._system_prompt)  # type: ignore[call-arg]
        return handler(updated_request)

    def wrap_tool_call(  # type: ignore[override]
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage],
    ) -> ToolMessage:
        """Sync stub. Use awrap_tool_call for full functionality."""
        return handler(request)
