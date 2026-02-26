"""OpenAgent package.

OpenAgent is an Agent SDK (supporting OpenAI-compatible LLMs) similar to
Anthropic's Claude Agent SDK.

Core Philosophy: Give agents a CLI-based computer, allowing them to work
like humans do.
"""

from openagent.harness.model import ModelProfile
from openagent.langchain import Agent, create_agent

__all__ = [
    "Agent",
    "ModelProfile",
    "create_agent",
]
