"""LangChain integration for ClawWork.

This module provides adapters and utilities for integrating ClawWork's
framework-agnostic tools and computer abstractions with LangChain.

If you delete this directory, all core ClawWork functionality
(tools, computer, types, prompts) should still work independently.

Main exports:
- Agent: ClawWork agent with managed resources
- create_agent: Create an ClawWork agent using LangChain
- to_langchain_tool: Convert BaseAgentTool to LangChain StructuredTool
- LangChainSubagentRunner: Executes subagents with isolated context
"""

from clawwork.langchain.adapter import to_langchain_tool
from clawwork.langchain.agent import Agent, create_agent
from clawwork.langchain.subagent import LangChainSubagentRunner

__all__ = [
    "Agent",
    "LangChainSubagentRunner",
    "create_agent",
    "to_langchain_tool",
]
