"""Agent middleware — the actual runtime for OpenAgent.

This middleware coordinates compaction, permission gating, skill injection,
and system reminder rules within LangChain's agent infrastructure.

Compaction logic is inlined (no separate controller class). The three-group
pre-model pipeline runs: intercepts -> appenders -> annotators.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NotRequired, Protocol

from langchain.agents.middleware.types import (
    AgentMiddleware as LangChainAgentMiddleware,
)
from langchain.agents.middleware.types import (
    AgentState,
    ToolCallRequest,
    hook_config,
)
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
    convert_to_openai_messages,
)
from langgraph.types import Command
from langgraph.types import Overwrite as LangGraphOverwrite

from openagent.harness import PermissionGate, PermissionResult, Reminder, evaluate_reminders
from openagent.harness.model import _FALLBACK_COMPACTION_THRESHOLD
from openagent.langchain.adapter import to_langchain_tool
from openagent.types import AgentContext, CompactionPhase

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from langchain_core.tools import BaseTool
    from langgraph.runtime import Runtime

    from openagent.harness.skills import SkillResolver
    from openagent.tools.base import BaseAgentTool
    from openagent.types import MCPServer, Skill

logger = logging.getLogger(__name__)


class ApprovalCallback(Protocol):
    """Callback for human-in-the-loop approval of tool calls.

    Examples:
        ```python
        async def cli_approval(
            tool_name: str,
            tool_args: dict[str, Any],
            approval_prompt: str | None,
        ) -> bool:
            response = input(f"Allow {tool_name}? [y/n]: ")
            return response.lower() == "y"
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


# Minimum messages required before compaction can trigger.
# A single summary message after compaction should not re-trigger.
_MIN_MESSAGES_FOR_COMPACTION = 2


def _extract_text_content(content: str | list[Any]) -> str:
    """Extract text from LangChain message content (str or list[block])."""
    if isinstance(content, str):
        return content
    return "".join(block if isinstance(block, str) else block.get("text", "") for block in content if isinstance(block, (str, dict)))


def _extract_summary(messages: Sequence[BaseMessage]) -> str:
    """Extract summary text from the last AIMessage."""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return _extract_text_content(msg.content)
    return ""


def _rebuild_message(msg: BaseMessage, new_content: str) -> BaseMessage:
    """Reconstruct a message with modified content, preserving metadata."""
    kwargs: dict[str, Any] = {"content": new_content}
    if msg.id is not None:
        kwargs["id"] = msg.id
    if isinstance(msg, ToolMessage):
        kwargs["tool_call_id"] = msg.tool_call_id
    return msg.__class__(**kwargs)


def _create_denied_response(
    request: ToolCallRequest,
    reason: str | None,
) -> ToolMessage:
    """Create a tool response for a denied action."""
    error_message = f"Permission denied: {reason}" if reason else "Permission denied"
    return ToolMessage(
        content=error_message,
        tool_call_id=request.tool_call.get("id", ""),
    )


def _detect_skill_call(messages: Sequence[BaseMessage]) -> str | None:
    """Detect if the most recent tool call was 'skill' and return the skill name.

    Returns None if no recent skill tool call found or if a HumanMessage
    already follows the skill ToolMessage (already injected).
    """
    if not messages:
        return None

    # Walk backwards: find the last ToolMessage
    # If we hit a HumanMessage first, skill was already injected
    last_tool_msg_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, HumanMessage):
            return None
        if isinstance(msg, ToolMessage):
            last_tool_msg_idx = i
            break

    if last_tool_msg_idx is None:
        return None

    tool_msg = messages[last_tool_msg_idx]
    if not isinstance(tool_msg, ToolMessage):
        return None  # unreachable, satisfies mypy
    tool_call_id = tool_msg.tool_call_id

    # Find the corresponding AIMessage with tool_calls
    for i in range(last_tool_msg_idx - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                if tc.get("id") == tool_call_id and tc.get("name") == "skill":
                    args: dict[str, str] = tc.get("args", {})
                    return args.get("skill")
            break  # Only check the nearest AIMessage

    return None


class OpenAgentState(AgentState):
    """Extended agent state with compaction tracking."""

    compaction_phase: NotRequired[CompactionPhase]


class AgentMiddleware(LangChainAgentMiddleware):
    """The OpenAgent runtime, implemented as LangChain middleware.

    Coordinates:
    - System prompt injection (first turn)
    - Compaction (3-phase inlined state machine)
    - Skill injection (appender)
    - Reminder rules (annotators)
    - Permission gating (tool call wrapper)

    Pre-model pipeline runs three ordered groups:
    1. Intercepts: compaction phases (may abort normal processing)
    2. Appenders: skill injection (adds messages)
    3. Annotators: reminder rules (injects into last message)
    """

    state_schema = OpenAgentState

    def __init__(
        self,
        *,
        tools: Sequence[BaseAgentTool[Any]],
        system_prompt: str,
        skills: Sequence[Skill] = (),
        mcps: Sequence[MCPServer] = (),
        permission_gate: PermissionGate,
        compaction_prompt: str,
        compaction_threshold: int = _FALLBACK_COMPACTION_THRESHOLD,
        using_default_threshold: bool = False,
        approval_callback: ApprovalCallback | None = None,
        skill_resolver: SkillResolver | None = None,
        reminders: Sequence[Reminder] = (),
        rebuild_callback: Callable[[str], Awaitable[list[BaseMessage]]],
    ) -> None:
        """Initialize the middleware.

        Args:
            tools: Agent tools (framework-agnostic).
            system_prompt: Assembled system prompt for first-turn injection.
            skills: Discovered skills.
            mcps: MCP server descriptors.
            permission_gate: Gate for validating tool calls.
            compaction_prompt: Prompt for requesting conversation summaries.
            compaction_threshold: Token count that triggers compaction.
            using_default_threshold: True when using the fallback threshold
                (no ModelProfile provided). Enables a warning log on trigger.
            approval_callback: Optional callback for human-in-the-loop approval.
            skill_resolver: Optional resolver for injecting skill content.
            reminders: Reminder rules for dynamic system-reminder injection.
            rebuild_callback: Callback that rebuilds messages after compaction.
                Receives summary text, returns [SystemMessage, HumanMessage].
        """
        self._tools = list(tools)
        self._system_prompt = system_prompt
        self._skills = list(skills)
        self._mcps = list(mcps)
        self._permission_gate = permission_gate
        self._compaction_prompt = compaction_prompt
        self._compaction_threshold = compaction_threshold
        self._using_default_threshold = using_default_threshold
        self._approval_callback = approval_callback
        self._skill_resolver = skill_resolver
        self._reminders = list(reminders)
        self._rebuild_callback = rebuild_callback
        self._tools_cache: list[BaseTool] | None = None

    @property
    def tools(self) -> Sequence[BaseTool]:  # type: ignore[override]
        """Get tools as LangChain tools (cached)."""
        if self._tools_cache is None:
            self._tools_cache = [to_langchain_tool(tool) for tool in self._tools]
        return self._tools_cache

    @staticmethod
    def _get_total_tokens(messages: Sequence[BaseMessage]) -> int | None:
        """Extract total_tokens from the last AIMessage's usage_metadata.

        Returns None if unavailable (e.g. fake models in tests).
        """
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                metadata = msg.usage_metadata
                if metadata is not None:
                    return metadata["total_tokens"]
                return None
        return None

    # --- Async hooks (primary implementations) ---

    async def abefore_model(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Three-group pre-model pipeline.

        Step 0: System prompt injection (first turn only).
        Group 1: Intercepts (compaction phases, early exit).
        Group 2: Appenders (skill injection).
        Group 3: Annotators (system reminders).
        """
        messages = list(state["messages"])
        need_overwrite = False

        # --- STEP 0: System prompt injection (first turn only) ---
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=self._system_prompt), *messages]
            need_overwrite = True

        # --- GROUP 1: Intercepts (compaction phases) ---
        phase = CompactionPhase(state.get("compaction_phase", CompactionPhase.NONE))

        if phase == CompactionPhase.REQUESTING:
            messages.append(HumanMessage(content=self._compaction_prompt))
            return {
                "messages": LangGraphOverwrite(messages),
                "compaction_phase": phase,
            }

        if phase == CompactionPhase.APPLYING:
            summary = _extract_summary(messages)
            rebuilt = await self._rebuild_callback(summary)
            return {
                "messages": LangGraphOverwrite(rebuilt),
                "compaction_phase": CompactionPhase.NONE,
            }

        # --- GROUP 2: Appenders (skill injection) ---
        if self._skill_resolver is not None:
            skill_name = _detect_skill_call(messages)
            if skill_name is not None:
                try:
                    content = await self._skill_resolver.load_content(skill_name)
                except (KeyError, RuntimeError):
                    content = None
                if content is not None:
                    messages = [*messages, HumanMessage(content=content)]
                    need_overwrite = True

        # --- GROUP 3: Annotators (system reminders) ---
        if self._reminders:
            # Evaluate against ORIGINAL messages (before our modifications)
            original_for_rules = state["messages"]
            openai_msgs = convert_to_openai_messages(original_for_rules)
            ctx = AgentContext(
                tools=self._tools,
                skills=self._skills,
                mcps=self._mcps,
            )
            prepends, appends = evaluate_reminders(self._reminders, openai_msgs, ctx)

            if prepends or appends:
                last_msg = messages[-1]
                content_str = _extract_text_content(last_msg.content)

                parts = [*prepends, content_str, *appends]
                new_content = "\n\n".join(part for part in parts if part)

                messages = [*messages[:-1], _rebuild_message(last_msg, new_content)]  # type: ignore[list-item]
                need_overwrite = True

        # --- RETURN ---
        if need_overwrite:
            return {"messages": LangGraphOverwrite(messages)}
        return None

    @hook_config(can_jump_to=["model"])
    async def aafter_model(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Compaction trigger — check token count after model response."""
        messages = state["messages"]
        phase = CompactionPhase(state.get("compaction_phase", CompactionPhase.NONE))

        # Trigger compaction if threshold exceeded
        if phase == CompactionPhase.NONE and len(messages) >= _MIN_MESSAGES_FOR_COMPACTION:
            token_count = self._get_total_tokens(messages)
            if token_count is not None and token_count >= self._compaction_threshold:
                if self._using_default_threshold:
                    logger.warning(
                        "Compaction triggered at %d tokens using fallback threshold %d. "
                        "Pass a ModelProfile to create_agent for model-aware compaction.",
                        token_count,
                        self._compaction_threshold,
                    )
                return {"compaction_phase": CompactionPhase.REQUESTING, "jump_to": "model"}

        # Advance state machine: LLM just generated the summary
        if phase == CompactionPhase.REQUESTING:
            return {"compaction_phase": CompactionPhase.APPLYING, "jump_to": "model"}

        return None

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        """Check permission before tool execution."""
        tool_name = request.tool_call["name"]
        tool_args = request.tool_call.get("args", {})

        decision = await self._permission_gate.check(tool_name, tool_args)

        if decision.result == PermissionResult.DENIED:
            return _create_denied_response(request, decision.reason)

        if decision.result == PermissionResult.NEEDS_APPROVAL:
            if self._approval_callback is None:
                return _create_denied_response(
                    request,
                    f"Action requires approval: {decision.approval_prompt or 'No details provided'}",
                )

            approved = await self._approval_callback(
                tool_name,
                tool_args,
                decision.approval_prompt,
            )

            if not approved:
                return _create_denied_response(request, "Action denied by user")

        return await handler(request)
