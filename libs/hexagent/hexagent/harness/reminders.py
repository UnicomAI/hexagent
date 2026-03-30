"""System reminder rules for dynamic message annotation.

Reminder rules evaluate conversation state and return content to inject
as ``<system-reminder>`` tags. Rules receive messages as OpenAI-compatible
dicts (framework-agnostic) and a context snapshot of agent capabilities.

Each rule is a callable: ``(messages, ctx) -> str | None``.
Returning ``None`` opts out. Returning a string triggers injection.
Position (prepend/append to last message) is metadata at registration time.

Built-in rules are defined at the bottom of this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from hexagent.prompts.content import load, substitute
from hexagent.prompts.tags import SYSTEM_REMINDER_TAG, Tag

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hexagent.tasks import TaskRegistry
    from hexagent.types import AgentContext

# OpenAI-compatible message format.
# Expected keys: "role" (str), "content" (str | list),
# optional "tool_calls", "tool_call_id".
Message = dict[str, Any]


@dataclass(frozen=True)
class Reminder:
    """A reminder rule with injection position metadata.

    Attributes:
        rule: Callable that evaluates messages and returns content or None.
        position: Where to inject the reminder into the last message.
    """

    rule: Callable[[Sequence[Message], AgentContext], str | None]
    position: Literal["prepend", "append"] = "prepend"


def evaluate_reminders(
    reminders: Sequence[Reminder],
    messages: Sequence[Message],
    ctx: AgentContext,
    tag: Tag = SYSTEM_REMINDER_TAG,
) -> tuple[list[str], list[str]]:
    """Evaluate reminder rules and return tagged strings ready for injection.

    All rules evaluate against the ORIGINAL message list (not each other's
    output). Each non-None result is wrapped in ``<tag>`` and sorted by
    position.

    Args:
        reminders: Rules to evaluate (in declared order).
        messages: Message history as OpenAI-compatible dicts.
        ctx: Snapshot of agent capabilities.
        tag: Callable tag to wrap each reminder.

    Returns:
        (prepends, appends) — tagged strings ready for injection.
    """
    prepends: list[str] = []
    appends: list[str] = []
    for reminder in reminders:
        content = reminder.rule(messages, ctx)
        if content is not None:
            wrapped = tag(content)
            if reminder.position == "prepend":
                prepends.append(wrapped)
            else:
                appends.append(wrapped)
    return prepends, appends


# ---------------------------------------------------------------------------
# Built-in reminder rules
# ---------------------------------------------------------------------------


# --- HARDCODED SKILLS FOR DEMO (Temporary override) ---
# Set this to a non-empty string to bypass automatic discovery
# e.g. "- pdf: Process PDF files\n- excel: Handle spreadsheets"
DEMO_HARDCODED_SKILLS: str | None = """
- pptx: 处理 .pptx 文件（创建、读取、编辑、合并、拆分）。支持幻灯片生成、图表添加。在处理演示文稿、deck 或 slides 时触发。请你注意，用户让你制作ppt的时候务必先触发此skills。
- canvas-design: Create beautiful visual art in .png and .pdf documents using design philosophy. You should use this skill when the user asks to create a poster, piece of art, design, or other static piece. Create original visual designs, never copying existing artists' work to avoid copyright violations.
- data-insight-report: Analyze tabular data (Excel, CSV, TSV, etc.) and generate insightful ECharts visualizations embedded in comprehensive data insight reports. Use when: analyzing spreadsheet data for insights, creating data visualization dashboards, generating interactive chart reports, building presentation-ready data insight reports, or when user needs to transform tabular data into actionable insights with visualizations.
- doc: Use when the task involves reading, creating, or editing `.docx` documents, especially when formatting or layout fidelity matters; prefer `python-docx` plus the bundled `scripts/render_docx.py` for visual checks.
- excel-xlsx: Create, inspect, and edit Microsoft Excel workbooks and XLSX files with reliable formulas, dates, types, formatting, recalculation, and template preservation. Use when (1) the task is about Excel, `.xlsx`, `.xlsm`, `.xls`, `.csv`, or `.tsv`; (2) formulas, formatting, workbook structure, or compatibility matter; (3) the file must stay reliable after edits.
- find-skills: Highest-priority skill discovery flow. MUST trigger when users ask to find/install skills (e.g. 技能, 找技能, find-skill, find-skills, install skill). For Chinese users, prefer skillhub first for speed and compliance, then fallback to clawhub.
- frontend-design: Create distinctive, production-grade frontend interfaces with high design quality. Use this skill when the user asks to build web components, pages, artifacts, posters, or applications (examples include websites, landing pages, dashboards, React components, HTML/CSS layouts, or when styling/beautifying any web UI). Generates creative, polished code and UI design that avoids generic AI aesthetics.
- mcp-builder: Guide for creating high-quality MCP (Model Context Protocol) servers that enable LLMs to interact with external services through well-designed tools. Use when building MCP servers to integrate external APIs or services, whether in Python (FastMCP) or Node/TypeScript (MCP SDK).
- pdf-generator: Generate professional PDFs from Markdown, HTML, data, or code.
- skill-creator: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, edit, or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
- theme-factory: Toolkit for styling artifacts with a theme. These artifacts can be slides, docs, reportings, HTML landing pages, etc. There are 10 pre-set themes with colors/fonts that you can apply to any artifact that has been creating, or can generate a new theme on-the-fly.
- web-artifacts-builder: Suite of tools for creating elaborate, multi-component claude.ai HTML artifacts using modern frontend web technologies (React, Tailwind CSS, shadcn/ui). Use for complex artifacts requiring state management, routing, or shadcn/ui components - not for simple single-file HTML/JSX artifacts.
- webapp-testing: Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs."""
# ------------------------------------------------------


def available_skills_reminder(
    messages: Sequence[Message],
    ctx: AgentContext,
) -> str | None:
    """Inject available skills list into the first user message.

    Fires only at the very beginning of a conversation session
    (single user message, no prior model responses) when skills
    are available (or when using DEMO_HARDCODED_SKILLS).
    """
    _max_initial_messages = 2  # At most: [system?, user]
    if not messages or len(messages) > _max_initial_messages or messages[-1].get("role") != "user":
        return None

    # Use hardcoded skills if provided, otherwise fallback to ctx.skills
    if DEMO_HARDCODED_SKILLS:
        formatted = DEMO_HARDCODED_SKILLS
    elif ctx.skills:
        formatted = "\n".join(f"- {s.name}: {s.description}" for s in ctx.skills)
    else:
        return None

    template = load("system_reminder_initial_available_skills")
    return substitute(template, **ctx.tool_name_vars, FORMATTED_SKILLS_LIST=formatted)


def task_completion_reminder(registry: TaskRegistry) -> Reminder:
    """Create a reminder that surfaces background task completions.

    Drains completed/failed tasks from the registry and formats them
    as ``<task-notification>`` blocks for the agent.

    Args:
        registry: The task registry to drain completions from.
    """

    def _rule(_messages: Sequence[Message], _ctx: AgentContext) -> str | None:
        completions = registry.drain_completions()
        if not completions:
            return None
        status_headers: dict[str, str] = {
            "completed": "A background task completed",
            "failed": "A background task failed",
        }
        parts = [
            f"{status_headers.get(c.status, f'Background task {c.status}')}:\n"
            f"<task-notification>\n"
            f"<task-id>{c.task_id}</task-id>\n"
            f"<kind>{c.kind}</kind>\n"
            f"<status>{c.status}</status>\n"
            f'<summary>Task "{c.description}" {c.status}</summary>\n'
            f"<result>{c.result.to_text()}</result>\n"
            f"</task-notification>"
            for c in completions
        ]
        return "\n\n".join(parts)

    return Reminder(rule=_rule, position="append")


BUILTIN_REMINDERS: Sequence[Reminder] = [
    Reminder(rule=available_skills_reminder, position="prepend"),
]
"""Default reminder rules for all sessions.

Note: :func:`task_completion_reminder` is also a built-in reminder but requires
a :class:`~hexagent.tasks.TaskRegistry` instance. It is added
unconditionally by the agent factory.
"""
