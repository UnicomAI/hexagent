"""Openagent come with planning and CLI tools."""

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from langchain.agents import create_agent as _create_langchain_agent
from langchain.agents.structured_output import ResponseFormat
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.cache.base import BaseCache
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Checkpointer

from openagent.middleware.computer import ComputerMiddleware

if TYPE_CHECKING:
    from openagent.computer import Computer

BASE_AGENT_PROMPT = """You are OpenAgent, a general-purpose agent that uses a computer to complete tasks like how human does."""

DEFAULT_MODEL = "openai:gpt-5"


def create_agent(
    computer: "Computer",
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    *,
    system_prompt: str | None = None,
    response_format: ResponseFormat | None = None,
    context_schema: type[Any] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph:
    """Create an OpenAgent agent.

    OpenAgent agents require a LLM that supports tool calling.

    This agent will by default have access to seven CLI tools:
    `bash`, `read`, `write`, `edit`, `ls`, `glob`, `grep`.

    NOTE: Currently only `bash` is fully implemented. Other tools are stubs
    that raise NotImplementedError and will be implemented in future versions.

    All CLI tools share a persistent bash session where state (working directory,
    environment variables, shell functions) persists across tool calls.

    Args:
        computer: The Computer instance for CLI tools.

            Can be `LocalNativeComputer` for local execution or `RemoteE2BComputer`
            for cloud sandbox execution.
        model: The model to use.

            Defaults to `openai:gpt-5`.

            Use the `provider:model` format (e.g., `openai:gpt-5.2`) to quickly switch between models.
        tools: The tools the agent should have access to.

            In addition to custom tools you provide, OpenAgent agents include built-in tools for
            CLI operations.
        system_prompt: The additional instructions the agent should have.

            Will go in the system prompt.
        response_format: A structured output response format to use for the agent.
        context_schema: The schema of the agent.
        checkpointer: Optional `Checkpointer` for persisting agent state between runs.
        store: Optional store for LangGraph runtime.
        debug: Whether to enable debug mode. Passed through to the underlying langchain agent.
        name: The name of the agent. Passed through to the underlying langchain agent.
        cache: The cache to use for the agent. Passed through to the underlying langchain agent.

    Returns:
        A configured OpenAgent agent.
    """
    if model is None:
        model = init_chat_model(DEFAULT_MODEL)
    elif isinstance(model, str):
        model = init_chat_model(model)

    middleware = [
        ComputerMiddleware(computer=computer),
    ]

    return _create_langchain_agent(
        model,
        system_prompt=system_prompt + "\n\n" + BASE_AGENT_PROMPT if system_prompt else BASE_AGENT_PROMPT,
        tools=tools,
        middleware=middleware,
        response_format=response_format,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit": 1000})
