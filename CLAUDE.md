# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**HexAgent** is an agent harness — a runtime that gives LLM agents access to a computer via the terminal. This monorepo contains:

| Package | Description |
|---------|-------------|
| `libs/hexagent` | Core framework library (Python 3.11+) |
| `libs/hexagent_demo` | Desktop Chat + Cowork app (FastAPI + React + Electron) |

## Commands

### Core Library (`libs/hexagent`)

```bash
cd libs/hexagent

# Install dependencies
uv sync --group test

# Run tests
make test                                              # Unit tests with coverage
make integration_test                                  # Integration tests (requires API keys)
uv run pytest tests/unit_tests/path/to/test_file.py   # Single test file
uv run pytest tests/unit_tests/path/to/test_file.py::test_name -v  # Single test

# Code quality
make lint              # Ruff + mypy strict
make format            # Auto-fix formatting
```

### Demo Backend (`libs/hexagent_demo/backend`)

```bash
cd libs/hexagent_demo/backend

uv sync
uv run uvicorn hexagent_api.main:app --host 127.0.0.1 --port 8000
```

### Demo Frontend (`libs/hexagent_demo/frontend`)

```bash
cd libs/hexagent_demo/frontend

npm install
npm run dev            # Development server on :5173
npm run build          # Production build
npm run lint           # ESLint
```

### Desktop App (`libs/hexagent_demo/electron`)

```bash
cd libs/hexagent_demo/electron

npm install
npm run dev            # Development mode
npm run build:mac      # macOS build
npm run build:win      # Windows build
```

## Architecture

### Core Library (`libs/hexagent`)

```
hexagent/
├── computer/          # Pluggable execution environments
│   ├── base.py        #   Computer protocol (start/stop/run/upload/download)
│   ├── local/         #   LocalNativeComputer, LocalVMComputer (Lima/WSL)
│   └── remote/        #   RemoteE2BComputer (cloud sandbox)
├── harness/           # Runtime augmentation layer
│   ├── definition.py  #   AgentDefinition for subagent specs
│   ├── model.py       #   ModelProfile for LLM + context window config
│   ├── environment.py #   Runtime context (pwd, git, platform)
│   ├── permission.py  #   Safety rules and permission gating
│   ├── reminders.py   #   Dynamic message annotation system
│   └── skills.py      #   Skill discovery and lazy loading
├── tools/             # Built-in tools
│   ├── base.py        #   BaseAgentTool[ParamsT] abstract class
│   ├── cli/           #   Bash, Read, Write, Edit, Glob, Grep
│   ├── web/           #   WebSearch, WebFetch + provider plugins
│   └── task/          #   Agent (subagent spawning), TaskOutput, TaskStop
├── prompts/           # Composable prompt system
│   ├── content.py     #   Markdown fragment loader
│   ├── sections.py    #   Section-based composition
│   └── fragments/     #   35+ .md prompt files
├── mcp/               # Model Context Protocol integration
└── langchain/         # LangChain/LangGraph integration (isolated)
```

Key principle: **The core library is framework-agnostic.** LangChain imports are confined to `langchain/`. Tools, types, and computer abstractions have no LangChain dependency.

### Demo App (`libs/hexagent_demo`)

```
hexagent_demo/
├── backend/hexagent_api/
│   ├── main.py              # FastAPI app
│   ├── agent_manager.py     # Agent lifecycle and caching
│   ├── config.py            # Configuration persistence
│   └── routes/              # API endpoints (chat, config, skills, sessions)
├── frontend/src/
│   ├── components/          # 30+ React components
│   ├── tools/               # Tool result renderers with registry
│   └── store.ts             # Reducer-based state management
└── electron/                # Desktop packaging
```

Two operating modes:
- **Chat Mode**: Cloud sandbox via E2B, shared across conversations
- **Cowork Mode**: Local VM (Lima/WSL), per-conversation isolation

## Code Conventions

### Python (Core Library)

- **Typing**: MyPy strict mode (`mypy --strict`)
- **Docstrings**: Google style, required on all public APIs
- **Async**: All session/tool operations are async
- **Testing**: pytest-asyncio with `asyncio_mode = "auto"` (no decorators needed)
- **Test naming**: `test_<action>_<condition>_<expected_result>`

### Architecture Principles

1. **Testability** — Every module testable in isolation without complex mocks
2. **Composability** — Small, single-purpose units with explicit I/O. No hidden state.
3. **Minimal Dependencies** — Changes to module A require understanding only module A
4. **Agent-First** — Tools and results designed for agent ergonomics, not humans
5. **Idempotency** — Operations safely repeatable; retries don't cause side effects

### Status

Pre-Experimental (0.0.x). Backward compatibility is not a concern. Clean architecture and code quality win over API stability.

## Key Abstractions

### Computer Protocol

The foundational abstraction. Every agent gets a computer — a pluggable execution environment:

```python
class Computer(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def run(self, command: str, timeout: int | None) -> CLIResult: ...
    async def upload(self, src: Path, dst: Path) -> None: ...
    async def download(self, src: Path, dst: Path) -> None: ...
```

This separation means the agent runtime (API keys, source code, config) is isolated from the computer it controls (terminal, filesystem, user files).

### Harness System

The runtime augmentation layer wraps the raw LLM:
- **Environment detection** — Working directory, git status, platform
- **Context compaction** — 3-phase automatic summarization (NONE → REQUESTING → APPLYING)
- **Permission gating** — Safety rules validate tool calls before execution
- **Skill discovery** — Scans filesystem paths for SKILL.md-based skills
- **Dynamic reminders** — Injects `<system-reminder>` tags based on conversation state

### Tool Pattern

Extend `BaseAgentTool[ParamsT]` to create custom tools:

```python
class MyToolInput(BaseModel):
    query: str = Field(description="The search query")

class MyTool(BaseAgentTool[MyToolInput]):
    name = "MyTool"
    description = "Does something useful"
    args_schema = MyToolInput

    async def execute(self, params: MyToolInput) -> ToolResult:
        return ToolResult(output="Result here")
```
