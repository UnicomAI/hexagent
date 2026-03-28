"""ClawWork package.

ClawWork is an Agent SDK (supporting OpenAI-compatible LLMs) similar to
Anthropic's Claude Agent SDK.

Core Philosophy: Give agents a CLI-based computer, allowing them to work
like humans do.
"""

from clawwork.harness.definition import AgentDefinition
from clawwork.harness.model import ModelProfile
from clawwork.langchain import Agent, create_agent

__all__ = [
    "Agent",
    "AgentDefinition",
    "ModelProfile",
    "create_agent",
]
