"""LangChain integration for HexAgent.

This module provides adapters and utilities for integrating HexAgent's
framework-agnostic tools and computer abstractions with LangChain.

If you delete this directory, all core HexAgent functionality
(tools, computer, types, prompts) should still work independently.

Main exports:
- Agent: HexAgent agent with managed resources
- create_agent: Create an HexAgent agent using LangChain
- to_langchain_tool: Convert BaseAgentTool to LangChain StructuredTool
- LangChainSubagentRunner: Executes subagents with isolated context
"""

from hexagent.langchain.adapter import to_langchain_tool
from hexagent.langchain.agent import Agent, create_agent
from hexagent.langchain.subagent import LangChainSubagentRunner

__all__ = [
    "Agent",
    "LangChainSubagentRunner",
    "create_agent",
    "to_langchain_tool",
]
