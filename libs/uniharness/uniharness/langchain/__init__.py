"""LangChain integration for UniHarness.

This module provides adapters and utilities for integrating UniHarness's
framework-agnostic tools and computer abstractions with LangChain.

If you delete this directory, all core UniHarness functionality
(tools, computer, types, prompts) should still work independently.

Main exports:
- Agent: UniHarness agent with managed resources
- create_agent: Create an UniHarness agent using LangChain
- to_langchain_tool: Convert BaseAgentTool to LangChain StructuredTool
- LangChainSubagentRunner: Executes subagents with isolated context
"""

from uniharness.langchain.adapter import to_langchain_tool
from uniharness.langchain.agent import Agent, create_agent
from uniharness.langchain.subagent import LangChainSubagentRunner

__all__ = [
    "Agent",
    "LangChainSubagentRunner",
    "create_agent",
    "to_langchain_tool",
]
