"""Prompt infrastructure for building agent system prompts.

This package provides two layers:
- Content: .md fragment files with ``{variable}`` holes
- Composition: SystemPromptAssembler with RECIPE (ordered fragment refs)
"""

from openagent.prompts.assembler import SystemPromptAssembler
from openagent.prompts.library import PromptLibrary

__all__ = [
    "PromptLibrary",
    "SystemPromptAssembler",
]
