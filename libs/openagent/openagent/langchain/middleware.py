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
from langgraph.types import Command as LangGraphCommand
from langgraph.types import Overwrite as LangGraphOverwrite

from openagent.harness import PermissionGate, PermissionResult, Reminder, evaluate_reminders
from openagent.langchain.adapter import to_langchain_tool
from openagent.prompts import RESUMED_SESSION, compose, load, substitute
from openagent.prompts.tags import SYSTEM_REMINDER_TAG
from openagent.types import AgentContext, CompactionPhase

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from langchain_core.tools import BaseTool
    from langgraph.runtime import Runtime

    from openagent.harness.model import ModelProfile
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
    - System prompt injection (before-agent, once per invocation)
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
        model: ModelProfile,
        tools: Sequence[BaseAgentTool[Any]],
        system_prompt: str,
        permission_gate: PermissionGate,
        skills: Sequence[Skill] = (),
        mcps: Sequence[MCPServer] = (),
        skill_resolver: SkillResolver | None = None,
        reminders: Sequence[Reminder] = (),
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        """Initialize the middleware.

        Args:
            model: The main model profile.  The middleware extracts
                ``compaction_threshold`` from it.
            tools: Agent tools (framework-agnostic).
            system_prompt: Assembled system prompt for first-turn injection.
            permission_gate: Gate for validating tool calls.
            skills: Discovered skills.
            mcps: MCP server descriptors.
            skill_resolver: Optional resolver for injecting skill content.
            reminders: Reminder rules for dynamic system-reminder injection.
            approval_callback: Optional callback for human-in-the-loop approval.
        """
        self._model = model
        self._system_prompt = system_prompt
        self._tools = list(tools)
        self._mcps = list(mcps)
        self._skills = list(skills)
        self._skill_resolver = skill_resolver
        self._reminders = list(reminders)
        self._permission_gate = permission_gate
        self._approval_callback = approval_callback
        self._compaction_prompt = load("user_prompt_compaction_request")
        self._summary_template = load("user_prompt_compaction_summary_rebuild")
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

    async def _rebuild_after_compaction(self, summary: str) -> list[BaseMessage]:
        """Rebuild messages after compaction.

        1. Re-discovers skills from filesystem (live snapshot)
        2. Composes fresh system prompt using RESUMED_SESSION profile
        3. Returns [SystemMessage(new_prompt), HumanMessage(summary)]
        """
        current_skills: list[Skill] = []
        if self._skill_resolver is not None:
            current_skills = await self._skill_resolver.discover()

        ctx = AgentContext(tools=self._tools, skills=current_skills, mcps=self._mcps)
        new_system_prompt = compose(RESUMED_SESSION, ctx)
        summary_content = substitute(self._summary_template, SUMMARY_CONTENT=summary)

        return [
            SystemMessage(content=new_system_prompt),
            HumanMessage(content=summary_content),
        ]

    # --- Async hooks (primary implementations) ---

    async def abefore_agent(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """One-time setup before agent execution starts.

        Injects the system prompt if not already present.
        """
        messages = list(state["messages"])
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=self._system_prompt), *messages]
            return {"messages": LangGraphOverwrite(messages)}
        return None

    async def abefore_model(
        self,
        state: AgentState,
        _runtime: Runtime[Any] | None = None,
    ) -> dict[str, Any] | None:
        """Three-group pre-model pipeline.

        Group 1: Intercepts (compaction phases, early exit).
        Group 2: Appenders (skill injection).
        Group 3: Annotators (system reminders).
        """
        messages = list(state["messages"])

        # --- GROUP 1: Intercepts (compaction phases) ---
        phase = CompactionPhase(state.get("compaction_phase", CompactionPhase.NONE))

        if phase == CompactionPhase.REQUESTING:
            appended = [HumanMessage(content=self._compaction_prompt)]
            return {
                "messages": appended,
                "compaction_phase": phase,
            }

        if phase == CompactionPhase.APPLYING:
            last = messages[-1]
            if not isinstance(last, AIMessage):
                msg = (
                    f"Compaction state machine bug: APPLYING phase requires "
                    f"the model's summary as the last message (AIMessage), "
                    f"but got {type(last).__name__}. "
                )
                raise TypeError(msg)
            summary = _extract_text_content(last.content)
            rebuilt = await self._rebuild_after_compaction(summary)
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
                except (KeyError, RuntimeError) as exc:
                    template = load("system_reminder_skill_launch_failure")
                    content = SYSTEM_REMINDER_TAG(
                        substitute(template, SKILL_NAME=skill_name, FAILURE_MSG=repr(exc)),
                    )
                appended = [HumanMessage(content=content)]
                return {
                    "messages": appended,
                }

        # --- GROUP 3: Annotators (system reminders) ---
        if self._reminders:
            openai_msgs = convert_to_openai_messages(messages)
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

                patched = [*messages[:-1], _rebuild_message(last_msg, new_content)]
                return {
                    "messages": LangGraphOverwrite(patched),
                }

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
            threshold = self._model.compaction_threshold
            assert threshold is not None  # noqa: S101  # always set by __post_init__
            if token_count is not None and token_count >= threshold:
                return {"compaction_phase": CompactionPhase.REQUESTING, "jump_to": "model"}

        # Advance state machine: LLM just generated the summary
        if phase == CompactionPhase.REQUESTING:
            return {"compaction_phase": CompactionPhase.APPLYING, "jump_to": "model"}

        return None

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | LangGraphCommand[Any]]],
    ) -> ToolMessage | LangGraphCommand[Any]:
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
