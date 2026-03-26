"""Self-contained section functions for system prompt assembly.

Each section function has the signature ``(AgentContext) -> str | None``.
It loads its own content, resolves its own variables, and decides its own
inclusion (returning ``None`` to opt out).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from hexagent.prompts.content import find, load, substitute

if TYPE_CHECKING:
    from hexagent.harness.definition import AgentDefinition
    from hexagent.types import AgentContext


# ---------------------------------------------------------------------------
# Section functions — each is (AgentContext) -> str | None
# ---------------------------------------------------------------------------


def identity(_ctx: AgentContext) -> str | None:
    """Agent identity and help links. Always included."""
    return load("system_prompt_identity")


def agency(_ctx: AgentContext) -> str | None:
    """Agency guidelines. Always included."""
    return load("system_prompt_agency")


def doing_tasks(_ctx: AgentContext) -> str | None:
    """Software engineering task guidance. Always included."""
    return load("system_prompt_doing_tasks")


def executing_actions_with_care(_ctx: AgentContext) -> str | None:
    """Reversibility and blast-radius policy. Always included."""
    return load("system_prompt_executing_actions_with_care")


def tone_and_style(ctx: AgentContext) -> str | None:
    """Output style, objectivity, no time estimates. Always included."""
    return substitute(load("system_prompt_tone_and_style"), **ctx.tool_name_vars)


def environment(ctx: AgentContext) -> str | None:
    """Environment description."""
    if ctx.environment is None:
        return None
    env = ctx.environment
    return substitute(
        load("system_prompt_environment"),
        WORKING_DIR=env.working_dir,
        IS_GIT_REPO=str(env.is_git_repo).lower(),
        PLATFORM=env.platform,
        SHELL=env.shell,
        OS_VERSION=env.os_version,
        TODAY_DATE=env.today_date.strftime("%a %b %d, %Y"),
        MODEL_NAME=ctx.model_name,
    )


def _mnt_dirs(working_dir: str) -> tuple[str, str]:
    """Derive mnt output/upload paths from working_dir.

    In cowork mode (working_dir starts with ``/sessions``), paths are
    scoped under the session directory. Otherwise they sit at the root.

    Returns:
        (mnt_outputs_dir, mnt_uploads_dir)
    """
    from pathlib import PurePosixPath

    if working_dir.startswith("/sessions"):
        base = PurePosixPath(working_dir)
        return str(base / "mnt" / "outputs"), str(base / "mnt" / "uploads")
    return "/mnt/outputs", "/mnt/uploads"


def computer_use(ctx: AgentContext) -> str | None:
    """Computer use instructions including environment info."""
    if ctx.environment is None:
        return None
    env = ctx.environment
    mnt_outputs_dir, mnt_uploads_dir = _mnt_dirs(env.working_dir)

    # The template references tool names that may not be registered
    # (e.g. Skill, PresentToUser). Provide canonical defaults so
    # substitution never fails on missing tool name vars.
    tool_vars = {
        "SKILL_TOOL_NAME": "Skill",
        "PRESENTTOUSER_TOOL_NAME": "PresentToUser",
    }
    tool_vars.update(ctx.tool_name_vars)

    return substitute(
        load("system_prompt_computer_use"),
        WORKING_DIR=env.working_dir,
        PLATFORM=env.platform,
        SHELL=env.shell,
        OS_VERSION=env.os_version,
        TODAY_DATE=env.today_date.strftime("%a %b %d, %Y"),
        MODEL_NAME=ctx.model_name,
        MNT_OUTPUTS_DIR=mnt_outputs_dir,
        MNT_UPLOADS_DIR=mnt_uploads_dir,
        **tool_vars,
    )


def using_your_tools(ctx: AgentContext) -> str | None:
    """Parallel calling and tool-over-bash preference."""
    if not ctx.tools:
        return None
    # Provide canonical defaults for tool names that may not be registered.
    tool_vars = {
        "TODOWRITE_TOOL_NAME": "TodoWrite",
        "AGENT_TOOL_NAME": "Agent",
        "PRESENTTOUSER_TOOL_NAME": "PresentToUser",
    }
    tool_vars.update(ctx.tool_name_vars)
    return substitute(load("system_prompt_using_your_tools"), **tool_vars)


def _format_available_agents(agents: dict[str, AgentDefinition]) -> str:
    """Format agent definitions for the ``${AVAILABLE_AGENTS}`` placeholder."""
    lines = ["- general-purpose: General-purpose agent for any task. (Tools: *)"]
    for name, defn in agents.items():
        lines.append(f"- {name}: {defn.description} (Tools: {', '.join(defn.tools)})")
    return "\n".join(lines)


def tool_instructions(ctx: AgentContext) -> str | None:
    """Per-tool usage instructions with supplementary fragments."""
    if not ctx.tools:
        return None

    today = date.today()  # noqa: DTZ011
    shared_vars = {
        **ctx.tool_name_vars,
        "CURRENT_DATE": today.isoformat(),
        "CURRENT_YEAR": str(today.year),
        "PREVIOUS_YEAR": str(today.year - 1),
        "GIT_PARALLEL_NOTE": (
            "You can call multiple tools in a single response. "
            "When multiple independent pieces of information are requested "
            "and all commands are likely to succeed, "
            "run multiple tool calls in parallel for optimal performance."
        ),
        "AVAILABLE_AGENTS": _format_available_agents(ctx.agents),
    }

    tool_sections: list[str] = []

    for tool in ctx.tools:
        file_key = tool.name.lower()
        main_key = f"tool_instruction_{file_key}"

        # Try .md file first, fall back to tool.instruction
        try:
            raw = load(main_key)
        except KeyError:
            if tool.instruction:
                tool_sections.append(f"## {tool.name}\n\n{tool.instruction}")
            continue

        parts: list[str] = [raw]

        # Discover and append supplementary fragments
        prefix = f"tool_instruction_{file_key}_"
        parts.extend(load(supp_key) for supp_key in find(prefix))

        content = "\n\n".join(parts)

        # Apply all shared substitutions (tool names, dates,
        # git_parallel_note). str.replace is a safe no-op for
        # vars not present in a given fragment.
        content = substitute(content, **shared_vars)

        tool_sections.append(f"## {tool.name}\n\n{content}")

    return "# Tools\n\n" + "\n\n---\n\n".join(tool_sections)


def mcps(ctx: AgentContext) -> str | None:
    """MCP server listing."""
    if not ctx.mcps:
        return None
    items = "\n".join(f"- **{m.name}**{': ' + m.instructions if m.instructions else ''}" for m in ctx.mcps)
    return f"# MCP Servers\n\nThe following MCP (Model Context Protocol) servers provide additional capabilities and tools.\n\n{items}"
