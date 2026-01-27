"""Tool implementations for openagent.

This module provides concrete tool implementations that follow Anthropic's
tool patterns. Tools in this module depend on core/ for result types and
computer/ for Computer implementations.

Base class:
- BaseAgentTool: Abstract base class for agent tools

Available tools:
- BashTool: Execute bash commands on a Computer
- ReadTool: Read file contents with line numbers
- WriteTool: Create or overwrite files
- EditTool: Perform string replacements in files
- LSTool: List directory contents
- GlobTool: Find files by pattern
- GrepTool: Search for patterns in files

Factory functions:
- create_bash_tool: Create the bash tool
- create_filesystem_tools: Create file operation tools (read, write, edit, ls, glob, grep)
- create_cli_tools: Create all CLI tools sharing a Computer instance
- create_cli_tools: Create all CLI tools sharing a Computer instance

Utilities:
- to_langchain_tool: Convert BaseAgentTool to LangChain BaseTool
"""

from openagent.tools.adapter import to_langchain_tool
from openagent.tools.base import BaseAgentTool
from openagent.tools.cli import (
    BashTool,
    EditTool,
    GlobTool,
    GrepTool,
    LSTool,
    ReadTool,
    WriteTool,
    create_bash_tool,
    create_cli_tools,
    create_filesystem_tools,
)

__all__ = [
    "BaseAgentTool",
    "BashTool",
    "EditTool",
    "GlobTool",
    "GrepTool",
    "LSTool",
    "ReadTool",
    "WriteTool",
    "create_bash_tool",
    "create_cli_tools",
    "create_filesystem_tools",
    "to_langchain_tool",
]
