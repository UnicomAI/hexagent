"""LangChain integration for OpenAgent.

This module provides adapters and utilities for integrating OpenAgent's
framework-agnostic tools and computer abstractions with LangChain.

If you delete this directory, all core OpenAgent functionality
(tools, computer, types, prompts) should still work independently.

Main exports:
- Agent: OpenAgent agent with managed resources
- create_agent: Create an OpenAgent agent using LangChain
- to_langchain_tool: Convert BaseAgentTool to LangChain StructuredTool
"""

from openagent.langchain.adapter import to_langchain_tool
from openagent.langchain.agent import Agent, create_agent

__all__ = [
    "Agent",
    "create_agent",
    "to_langchain_tool",
]
