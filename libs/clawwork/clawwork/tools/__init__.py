"""Tool implementations for clawwork.

This module provides concrete tool implementations that follow Anthropic's
tool patterns. Tools in this module depend on core/ for result types and
computer/ for Computer implementations.

Base class:
- BaseAgentTool: Abstract base class for agent tools

CLI tools:
- BashTool: Execute bash commands on a Computer
- ReadTool: Read file contents with line numbers
- WriteTool: Create or overwrite files
- EditTool: Perform string replacements in files
- GlobTool: Find files by pattern
- GrepTool: Search for patterns in files

Web tools:
- WebSearchTool: Search the web for information
- WebFetchTool: Fetch and extract content from web pages

Skill tools:
- SkillTool: Invoke specialized skills by name

Factory functions:
- create_bash_tool: Create the bash tool
- create_filesystem_tools: Create file operation tools (read, write, edit, glob, grep)
- create_cli_tools: Create all CLI tools sharing a Computer instance

For LangChain integration, see clawwork.langchain module.
"""

from typing import Any

from clawwork.tools.base import BaseAgentTool
from clawwork.tools.cli import (
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    ReadTool,
    WriteTool,
    create_bash_tool,
    create_cli_tools,
    create_filesystem_tools,
)
from clawwork.tools.skill import SkillTool
from clawwork.tools.task import TaskOutputTool, TaskStopTool
from clawwork.tools.task.agent import AgentTool
from clawwork.tools.todo import TodoWriteTool
from clawwork.tools.ui import PresentToUserTool
from clawwork.tools.web import (
    WebFetchTool,
    WebSearchTool,
    create_web_tools,
)
from clawwork.types import SubagentResult, SubagentRunner

BUILTIN_TOOLS: tuple[type[BaseAgentTool[Any]], ...] = (
    BashTool,
    ReadTool,
    WriteTool,
    EditTool,
    GlobTool,
    GrepTool,
    WebSearchTool,
    WebFetchTool,
    SkillTool,
    TodoWriteTool,
)
"""The canonical set of built-in tool classes.

ClawWork always has a computer — these tools are non-negotiable.
Everything that needs to know "what tools exist" derives from this
tuple (template variables, prompt fragment lookup, etc.).

Note: AgentTool lives in ``tools/task/agent.py`` and depends on the
:class:`~clawwork.types.SubagentRunner` protocol. TaskOutputTool and
TaskStopTool live in ``tools/task/`` and are assembled alongside AgentTool
by the agent factory.
"""

__all__ = [
    "BUILTIN_TOOLS",
    "AgentTool",
    "BaseAgentTool",
    "BashTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
    "PresentToUserTool",
    "ReadTool",
    "SkillTool",
    "SubagentResult",
    "SubagentRunner",
    "TaskOutputTool",
    "TaskStopTool",
    "TodoWriteTool",
    "WebFetchTool",
    "WebSearchTool",
    "WriteTool",
    "create_bash_tool",
    "create_cli_tools",
    "create_filesystem_tools",
    "create_web_tools",
]
