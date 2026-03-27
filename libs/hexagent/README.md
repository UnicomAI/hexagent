# HexAgent

The core Python library for building computer-using AI agents. HexAgent is an **agent harness** — the complete runtime layer that gives any LLM **access to a computer via the terminal**, completing tasks the way developers do.

**Vendor-agnostic.** Works with Anthropic, OpenAI, DeepSeek, open-weight models via OpenRouter, or any OpenAI-compatible endpoint. The model is a parameter — swap it without changing your agent.

> This is the library package. For the project overview and motivation, see the [main README](../../README.md).

## Installation

```bash
pip install hexagent
```

**Requirements:** Python 3.11+

### Optional dependencies

```bash
pip install hexagent[langsmith]    # LangSmith tracing
pip install hexagent[braintrust]   # Braintrust observability
pip install hexagent[observe]      # Both
```

## Quick Start

### Basic usage

```python
import asyncio
from hexagent import create_agent
from hexagent.computer import LocalNativeComputer

async def main():
    async with await create_agent(
        model="anthropic/claude-sonnet-4-20250514",
        computer=LocalNativeComputer(),
    ) as agent:
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": "Find all TODO comments in this project"}]
        })
        print(result["messages"][-1].content)

asyncio.run(main())
```

### Using any OpenAI-compatible model

```python
from hexagent import create_agent, ModelProfile
from hexagent.computer import LocalNativeComputer

model = ModelProfile(
    model="deepseek/deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key="your-key",
    context_window=64000,
)

async with await create_agent(
    model=model,
    computer=LocalNativeComputer(),
) as agent:
    result = await agent.ainvoke({"messages": [...]})
```

### Streaming responses

```python
async with await create_agent(
    model="anthropic/claude-sonnet-4-20250514",
    computer=LocalNativeComputer(),
) as agent:
    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": "Explain this codebase"}]},
        version="v2",
    ):
        # Process events: on_chat_model_stream, on_tool_start, on_tool_end, etc.
        print(event["event"], event.get("data"))
```

### Custom computer environment

```python
from hexagent import create_agent
from hexagent.computer import LocalNativeComputer, RemoteE2BComputer

# Local execution
async with await create_agent(
    model="anthropic/claude-sonnet-4-20250514",
    computer=LocalNativeComputer(),
) as agent:
    ...

# Cloud sandbox via E2B
async with await create_agent(
    model="anthropic/claude-sonnet-4-20250514",
    computer=RemoteE2BComputer(api_key="your-e2b-key"),
) as agent:
    ...
```

### Defining subagents

```python
from hexagent import create_agent, AgentDefinition
from hexagent.computer import LocalNativeComputer

agents = {
    "researcher": AgentDefinition(
        description="Research agent for deep-diving into codebases",
        system_prompt="You are a code research specialist...",
        tools=["Read", "Glob", "Grep", "WebSearch"],
        model="fast",  # Uses the fast model for efficiency
    ),
}

async with await create_agent(
    model="anthropic/claude-sonnet-4-20250514",
    computer=LocalNativeComputer(),
    agents=agents,
) as agent:
    ...
```

### MCP server integration

```python
async with await create_agent(
    model="anthropic/claude-sonnet-4-20250514",
    computer=LocalNativeComputer(),
    mcp_servers={
        "github": {"type": "http", "url": "https://mcp.github.com/mcp"},
        "filesystem": {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem"],
        },
    },
) as agent:
    ...
```

### Web search and fetch

```python
async with await create_agent(
    model="anthropic/claude-sonnet-4-20250514",
    computer=LocalNativeComputer(),
    search_provider=("tavily", "your-tavily-key"),
    fetch_provider=("jina", "your-jina-key"),
) as agent:
    ...
```

## API Reference

### `create_agent()`

The main entry point. Creates a fully configured agent with tools, skills, and middleware.

```python
async def create_agent(
    model: str | BaseChatModel | ModelProfile,          # LLM to use (required)
    computer: Computer,                                  # Execution environment (required)
    *,
    fast_model: str | BaseChatModel | ModelProfile | None = None,  # For subagent routing
    mcp_servers: Mapping[str, McpServerConfig] | None = None,      # MCP tool servers
    agents: Mapping[str, AgentDefinition] | None = None,           # Subagent definitions
    search_provider: SearchProvider | None = None,       # Web search provider
    fetch_provider: FetchProvider | None = None,         # Web fetch provider
    skill_paths: Sequence[str] = DEFAULT_SKILL_PATHS,    # Skill discovery directories
    system_prompt: str | None = None,                    # Override default prompt
    reminders: Sequence[Reminder] = BUILTIN_REMINDERS,   # Dynamic message annotations
    extra_tools: Sequence[BaseAgentTool[Any]] | None = None,  # Additional custom tools
    checkpointer: Checkpointer | None = None,            # LangGraph checkpointer
) -> Agent
```

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | `str \| BaseChatModel \| ModelProfile` | LLM specifier string (e.g. `"anthropic/claude-sonnet-4-20250514"`), a pre-configured LangChain model, or a `ModelProfile` with context window config. |
| `computer` | `Computer` | Execution environment for CLI tools. Use `LocalNativeComputer()` for local or `RemoteE2BComputer()` for cloud sandbox. |
| `fast_model` | same as `model` | Optional lightweight model for subagents marked with `model="fast"`. |
| `mcp_servers` | `Mapping[str, McpServerConfig]` | Dict mapping server names to MCP server configs. Supports `"stdio"`, `"sse"`, and `"http"` transports. |
| `agents` | `Mapping[str, AgentDefinition]` | Dict mapping subagent type names to their definitions. Parent agent spawns these via the `Agent` tool. |
| `search_provider` | `SearchProvider` | Web search backend. Pass `("tavily", api_key)` or `("brave", api_key)` for convenience. |
| `fetch_provider` | `FetchProvider` | Web fetch backend. Pass `("jina", api_key)` or `("firecrawl", api_key)` for convenience. |
| `skill_paths` | `Sequence[str]` | Directories to scan for SKILL.md-based skills. Defaults to `/mnt/skills`, `~/.hexagent/skills`, `.hexagent/skills`. |
| `system_prompt` | `str` | Override the auto-composed system prompt entirely. |
| `reminders` | `Sequence[Reminder]` | Dynamic message annotation rules evaluated on every turn. |
| `extra_tools` | `Sequence[BaseAgentTool]` | Additional tool instances appended to the built-in set. |
| `checkpointer` | `Checkpointer` | LangGraph checkpointer for conversation persistence. |

### `Agent`

The managed agent instance. Use as an async context manager.

```python
async with await create_agent(model=..., computer=...) as agent:
    # Invoke for a single response
    result = await agent.ainvoke({"messages": [...]})

    # Stream events
    async for event in agent.astream_events({"messages": [...]}, version="v2"):
        ...
```

**Properties:** `model`, `model_name`, `computer`, `tools`, `skills`, `mcps`, `agents`, `system_prompt`, `graph`

### `ModelProfile`

Configuration for an LLM with context window management.

```python
ModelProfile(
    model="anthropic/claude-sonnet-4-20250514",
    context_window=200000,          # Max tokens
    compaction_threshold=160000,    # When to trigger context compaction (default: 75% of context_window)
    api_key="...",                  # Optional: provider API key
    base_url="...",                 # Optional: custom endpoint
)
```

### `AgentDefinition`

Declarative specification for subagents.

```python
AgentDefinition(
    description="Short description shown to parent agent",
    system_prompt="Full system prompt for the subagent",
    tools=["Read", "Glob", "Grep"],  # Subset of available tools
    model="fast",                     # "fast" uses fast_model, "main" uses primary model
)
```

## Built-in Tools

| Tool | Description |
|------|-------------|
| `BashTool` | Execute shell commands (foreground or background with timeout) |
| `ReadTool` | Read file contents with line numbers, supports images |
| `WriteTool` | Create or overwrite files |
| `EditTool` | Exact string replacements in files |
| `GlobTool` | Pattern-based file search |
| `GrepTool` | Regex search across files (via ripgrep) |
| `WebSearchTool` | Web search via Tavily or Brave |
| `WebFetchTool` | Fetch and extract web page content via Jina or Firecrawl |
| `SkillTool` | Invoke extensible skills by name |
| `AgentTool` | Spawn subagents for parallel/specialized work |
| `TodoWriteTool` | Maintain structured todo lists |
| `PresentToUserTool` | Mark files for delivery to user |

### Custom tools

Extend `BaseAgentTool` to create your own:

```python
from hexagent.tools import BaseAgentTool
from hexagent.types import ToolResult
from pydantic import BaseModel, Field

class MyToolInput(BaseModel):
    query: str = Field(description="The search query")

class MyTool(BaseAgentTool[MyToolInput]):
    name = "MyTool"
    description = "Does something useful"
    args_schema = MyToolInput

    async def execute(self, params: MyToolInput) -> ToolResult:
        # Your implementation
        return ToolResult(output="Result here")

# Pass to create_agent
agent = await create_agent(
    model="...",
    computer=LocalNativeComputer(),
    extra_tools=[MyTool()],
)
```

## Key Concepts

### Computer Protocol

The foundational abstraction. Every agent gets a computer — a pluggable execution environment that abstracts *where* CLI tools run. This is what makes HexAgent agents general-purpose: the same tools work whether the agent is on your laptop, in a VM, or in the cloud.

Implementations must provide:

- `start()` / `stop()` — Lifecycle management (idempotent)
- `run(command, timeout)` — Execute shell commands
- `upload(src, dst)` / `download(src, dst)` — File transfer

Built-in implementations:
- **`LocalNativeComputer`** — Runs commands on the local machine via transient bash subprocesses
- **`LocalVMComputer`** — Runs inside a Lima VM (macOS) or WSL (Windows)
- **`RemoteE2BComputer`** — Runs in an E2B cloud sandbox with auto-pause/resume

### Harness System

The harness is the runtime augmentation layer — the "operating system" that wraps the raw LLM with everything it needs to function as a capable agent:

- **Environment detection** — Working directory, git status, platform, shell, timezone
- **Context compaction** — Automatic conversation summarization when approaching the context window limit (3-phase state machine: NONE → REQUESTING → APPLYING)
- **Permission gating** — Safety rules that validate tool calls before execution
- **Skill discovery** — Scans filesystem paths for SKILL.md-based extensible skills
- **Dynamic reminders** — Injects `<system-reminder>` tags based on conversation state (e.g. available skills, background task completions)

### Prompt Composition

System prompts are assembled from modular Markdown fragments in `prompts/fragments/`. Sections cover identity, agency, task execution, tool instructions, tone, and environment context. Supports `${VAR}` substitution and conditional inclusion.

### MCP Integration

Connect external tool servers via the [Model Context Protocol](https://modelcontextprotocol.io/). Supports `stdio`, `sse`, and `http` transports. Discovered tools are exposed to the agent as `mcp__<server>__<tool>`.

### Skills

Skills are filesystem-based extensions with a `SKILL.md` frontmatter file:

```markdown
---
name: pdf
description: Extract and process PDF documents
---

## Instructions
...
```

Default discovery paths: `/mnt/skills`, `~/.hexagent/skills`, `.hexagent/skills`.

## Architecture

```
hexagent/
├── __init__.py            # Public API: Agent, AgentDefinition, ModelProfile, create_agent
├── types.py               # Framework-agnostic core types (ToolResult, AgentContext, etc.)
├── tasks.py               # Background task lifecycle (TaskRegistry)
├── computer/              # Computer protocol + implementations
│   ├── base.py            #   Protocol definition, Mount, ExecutionMetadata
│   ├── local/             #   LocalNativeComputer, LocalVMComputer (Lima/WSL)
│   └── remote/            #   RemoteE2BComputer (E2B cloud sandbox)
├── harness/               # Agent runtime augmentation
│   ├── definition.py      #   AgentDefinition — declarative subagent specs
│   ├── model.py           #   ModelProfile — LLM + context window config
│   ├── environment.py     #   Runtime context detection (pwd, git, platform)
│   ├── permission.py      #   Safety rules and permission gating
│   ├── reminders.py       #   Dynamic message annotation system
│   └── skills.py          #   Skill discovery and lazy loading
├── tools/                 # Tool implementations
│   ├── base.py            #   BaseAgentTool[ParamsT] abstract class
│   ├── cli/               #   Bash, Read, Write, Edit, Glob, Grep
│   ├── web/               #   WebSearch, WebFetch + provider plugins
│   ├── task/              #   Agent (subagent spawning), TaskOutput, TaskStop
│   ├── skill.py           #   Skill invocation tool
│   ├── todo/              #   TodoWrite tool
│   └── ui/                #   PresentToUser tool
├── prompts/               # Composable prompt system
│   ├── content.py         #   Markdown fragment loader with variable substitution
│   ├── sections.py        #   Section-based prompt composition
│   └── fragments/         #   35+ .md prompt content files
├── mcp/                   # Model Context Protocol integration
│   ├── _client.py         #   Per-server MCP connection
│   ├── _connector.py      #   Multi-server connection manager
│   └── _tool.py           #   MCP tool wrapper as BaseAgentTool
└── langchain/             # LangChain/LangGraph integration (isolated module)
    ├── agent.py           #   Agent class + create_agent() factory
    ├── middleware.py       #   Runtime middleware (compaction, permissions, reminders)
    ├── adapter.py         #   BaseAgentTool → LangChain StructuredTool
    └── subagent.py        #   Isolated subagent execution
```

> **Note:** The core library is framework-agnostic. LangChain imports are confined to the `langchain/` module. Tools, types, and computer abstractions have no LangChain dependency.

## Development

```bash
cd libs/hexagent

# Install dependencies
uv sync --group test

# Run tests
make test              # Unit tests with coverage
make integration_test  # Integration tests (requires API keys)

# Code quality
make lint              # Ruff + mypy strict
make format            # Auto-fix formatting
```

See the [Contributing Guide](../../CONTRIBUTING.md) for more details.

## Status

**Pre-Experimental (0.0.x)** — API may change without notice. Clean architecture and code quality take priority over backward compatibility. We ship fast and refactor freely — backward compatibility constraints come later.
