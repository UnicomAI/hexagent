<p align="center">
  <img src=".github/images/logo.svg" alt="ClawWork" width="300"/>
</p>

<p align="center">
  <strong>Agent harness — give any LLM a computer. Ship any agent product.</strong>
</p>

<p align="center">
  <a href="https://github.com/an7tang/clawwork/actions/workflows/ci.yml"><img src="https://github.com/an7tang/clawwork/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
</p>

---

**ClawWork** is an open-source **agent harness**: the production runtime that gives any LLM a fully-equipped computer — terminal, filesystem, and shell — to complete tasks autonomously.

Unlike every other agent framework, ClawWork **separates the agent runtime from the computer it operates on**. Your agent gets a sandboxed machine; your runtime keeps its API keys, config, and source code private.

> **Why "harness" and not "framework"?** A framework gives you building blocks and says "assemble your own agent." A harness gives the agent a fully equipped runtime — tools, context management, safety, execution environments — so you focus on *what* the agent does, not *how* it executes. ([Read more](#agent-harness-vs-agent-framework))

## The Computer Layer

In Claude Code, Codex, and every LangChain agent, the agent runtime and the computer it controls are the same process. The agent can read its own source code, config files, and API keys. ClawWork's `Computer` protocol makes this separation explicit and pluggable — swap execution environments without changing a line of agent code.

```python
from clawwork import create_agent
from clawwork.computer import LocalNativeComputer, LocalVM, RemoteE2BComputer

# Development — run on your machine
agent = await create_agent(model="anthropic/claude-sonnet-4-20250514", computer=LocalNativeComputer())

# Security-sensitive — sandboxed VM (Lima on macOS, WSL on Windows)
agent = await create_agent(model="anthropic/claude-sonnet-4-20250514", computer=LocalVM())

# Production / multi-tenant — isolated cloud sandbox
agent = await create_agent(model="anthropic/claude-sonnet-4-20250514", computer=RemoteE2BComputer(api_key="..."))
```

```
┌───────────────────────────┐            ┌───────────────────────────┐
│     Agent Runtime         │            │     Agent's Computer      │
│     (your host)           │   run()    │     (sandboxed)           │
│                           │ ─────────> │                           │
│  - LLM API keys           │   start()  │  - Terminal + filesystem  │
│  - Agent source code      │   upload() │  - User's project files   │
│  - Harness config         │   stop()   │  - Installed tools        │
│  - Middleware & hooks     │            │                           │
│                           │            │  Cannot access runtime    │
└───────────────────────────┘            └───────────────────────────┘
```

Three built-in implementations cover every deployment scenario:

| Computer | Environment | Use case |
|---|---|---|
| `LocalNativeComputer` | Host shell | Development, trusted agents |
| `LocalVM` | Lima (macOS) / WSL (Windows) | Security-sensitive work, Cowork products |
| `RemoteE2BComputer` | E2B cloud sandbox | Production, multi-tenant, CI/CD |

Implement the `Computer` protocol to add your own — Docker, Kubernetes pods, or any remote execution target.

## Quick Start

```bash
pip install clawwork
```

### Minimal example

```python
import asyncio
from clawwork import create_agent
from clawwork.computer import LocalNativeComputer

async def main():
    async with await create_agent(
        model="anthropic/claude-sonnet-4-20250514",  # or any LLM
        computer=LocalNativeComputer(),
    ) as agent:
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": "Find all TODO comments in this project"}]
        })
        print(result["messages"][-1].content)

asyncio.run(main())
```

### Use any model

```python
from clawwork import create_agent, ModelProfile
from clawwork.computer import LocalNativeComputer

# DeepSeek, Qwen, Llama, Mistral — anything OpenAI-compatible
model = ModelProfile(
    model="deepseek/deepseek-chat",
    base_url="https://api.deepseek.com/v1",
    api_key="your-key",
    context_window=64000,
)

agent = await create_agent(model=model, computer=LocalNativeComputer())
```

### Add subagents, MCP servers, web tools

```python
from clawwork import create_agent, AgentDefinition
from clawwork.computer import LocalNativeComputer

agent = await create_agent(
    model="anthropic/claude-sonnet-4-20250514",
    computer=LocalNativeComputer(),
    # Subagents for parallel specialized work
    agents={
        "researcher": AgentDefinition(
            description="Deep-dives into codebases",
            tools=["Read", "Glob", "Grep", "WebSearch"],
            model="fast",
        ),
    },
    # MCP tool servers
    mcp_servers={
        "github": {"type": "http", "url": "https://mcp.github.com/mcp"},
    },
    # Web capabilities
    search_provider=("tavily", "your-key"),
    fetch_provider=("jina", "your-key"),
)
```

### Run in a cloud sandbox

```python
from clawwork import create_agent
from clawwork.computer import RemoteE2BComputer

# Fully isolated cloud execution — no local risk
agent = await create_agent(
    model="openai/gpt-4o",
    computer=RemoteE2BComputer(api_key="your-e2b-key"),
)
```

See [`libs/clawwork/README.md`](libs/clawwork/README.md) for the full API reference.

## What Can You Build?

One harness powers four product types — no other agent SDK does this:

| Product Type | Description | Example |
|---|---|---|
| **CLI Coding Agent** | Terminal-native agent that lives in your shell, reads your codebase, writes and runs code autonomously | [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview), [Gemini CLI](https://github.com/google-gemini/gemini-cli) |
| **Chatbot** | Conversational AI assistant — you ask, it answers, with web search, file uploads, and tool use in the loop | [ChatGPT](https://chatgpt.com/), [Claude Chat](https://claude.ai/) |
| **Cowork** | Desktop agent that works on your local files, folders, and apps — completing knowledge work tasks autonomously while you steer | [Claude Cowork](https://www.anthropic.com/product/claude-cowork) |
| **Autonomous Agent** | Headless agent that runs tasks end-to-end without supervision | [OpenClaw](https://github.com/openclaw/openclaw), [Devin](https://devin.ai/) |

The [`clawwork_demo`](libs/clawwork_demo/) app ships with ready-to-use **Chat** and **Cowork** modes as concrete examples.

## Features

### Core Architecture

- **Computer Protocol** — Pluggable execution environments (local, VM, cloud) with full runtime isolation. The agent's computer is a separate process from the agent itself.
- **Model-agnostic** — Anthropic, OpenAI, DeepSeek, open-weight models via OpenRouter, or any OpenAI-compatible endpoint. Swap models without changing your agent.
- **Context engineering** — Automatic 3-phase compaction keeps agents effective across long sessions. Context is an architectural concern, not an afterthought.

### Production Capabilities

- **12+ built-in tools** — Bash, Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, plus extensible skills and MCP servers
- **Subagent orchestration** — Spawn specialized child agents (foreground + background) with isolated contexts and filtered tool sets
- **MCP native** — First-class [Model Context Protocol](https://modelcontextprotocol.io/) support via stdio, SSE, or HTTP transports
- **Permission gating** — Multi-layer safety rules validate every tool call before execution with human-in-the-loop approval flows
- **Skills system** — Filesystem-based extensions with SKILL.md metadata and on-demand loading
- **System reminders** — Rule-based context injection before model calls (`<system-reminder>` mechanism)
- **Web providers** — Pluggable search (Tavily/Brave) and fetch (Jina/Firecrawl) backends
- **Composable, not magical** — Small modules with explicit I/O. No hidden state. Every piece is testable and replaceable.

### How ClawWork Compares

| | ClawWork | Claude Agent SDK | LangChain Deep Agents |
|---|---|---|---|
| **Open source** | MIT | MIT | MIT |
| **Model-agnostic** | Any LLM | Claude only | Any LLM |
| **Runtime / Computer separation** | Yes (`Computer` protocol) | No (same process) | No (virtual filesystem) |
| **Computer environments** | Local + VM + Cloud (E2B) | Local only | Pluggable sandboxes |
| **Multi-product** (Chat, Code, Cowork, Autonomous) | Yes, from one harness | No (CLI-focused) | Assemble yourself |
| **Context compaction** | 3-phase automatic | Automatic | 3-tier (offload + truncate + summarize) |
| **Subagent orchestration** | Built-in (foreground + background) | Built-in (no nesting) | Built-in |
| **MCP support** | Native | Native | Via adapters |
| **Skill / plugin system** | Filesystem-based (SKILL.md) | Filesystem-based | Filesystem-based (SKILL.md) |
| **Observability** | LangSmith / Braintrust | None built-in | LangSmith |
| **Language** | Python | Python + TypeScript | Python + TypeScript |

## How the Harness Works

```
┌─────────────────────────────────────────────────────────────────┐
│                        Agent Harness                            │
│                                                                 │
│  ┌───────────┐  ┌──────────────┐  ┌───────────┐                 │
│  │  Prompt   │  │  Middleware  │  │   Tools   │                 │
│  │  System   │  │  Pipeline    │  │           │                 │
│  │           │  │              │  │ Bash,Read │                 │
│  │ Fragments │  │ Compaction   │  │ Write,Edit│                 │
│  │ Sections  │  │ Permissions  │  │ Glob,Grep │                 │
│  │ Variables │  │ Reminders    │  │ Web,MCP   │                 │
│  │           │  │ Image Adapt  │  │ Skills    │                 │
│  └───────────┘  └──────────────┘  │ Subagents │                 │
│                                   └───────────┘                 │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  Skills   │  │  MCP Client  │  │  Environment Detection   │  │
│  │  System   │  │  (stdio/sse/ │  │  (pwd, git, platform,    │  │
│  │           │  │   http)      │  │   shell, timezone)       │  │
│  └───────────┘  └──────────────┘  └──────────────────────────┘  │
└───────────────────────┬─────────────────────────────────────────┘
          ▲             │                       │
          │ LLM         │ Computer Protocol     │ Tool calls
          │ responses   │                       ▼
    ┌──────────┐  ┌─────┴────────────────────────────┐
    │ Any LLM  │  │ Computer (Local / VM / Cloud)    │
    │ Provider │  │ Terminal + Filesystem            │
    └──────────┘  └──────────────────────────────────┘
```

| Component | What it does |
|---|---|
| **Computer Protocol** | Pluggable execution environments — `LocalNativeComputer` (your machine), `LocalVM` (Lima/WSL), `RemoteE2BComputer` (cloud sandbox) |
| **Tool System** | 12+ built-in tools plus custom `BaseAgentTool` extension and MCP server integration |
| **Prompt Composition** | Modular system prompt built from 35+ Markdown fragments with variable substitution |
| **Middleware Pipeline** | Pre-model hooks: context compaction, permission gating, skill injection, image adaptation, dynamic reminders |
| **Subagent Orchestration** | Spawn child agents with isolated contexts, filtered tool sets, and background execution |
| **Skill Discovery** | Filesystem-based extensions with SKILL.md metadata and lazy loading |

## Agent Harness vs Agent Framework

The AI agent ecosystem has converged on a [clear taxonomy](https://blog.langchain.com/agent-frameworks-runtimes-and-harnesses-oh-my/):

| | Framework | Runtime | Harness |
|---|---|---|---|
| **What it is** | Building blocks (tools, prompts, memory) | Durable execution engine | Complete agent operating system |
| **Analogy** | A toolkit | A job scheduler | An OS for the agent |
| **You build** | Everything from scratch | Orchestration logic | Your agent's purpose |
| **Examples** | LangChain, CrewAI, Semantic Kernel | LangGraph, Temporal | ClawWork, Claude Code, OpenHands |

A framework says: *"Here are components. Assemble your agent."*

A harness says: *"Here is a fully equipped computer. Tell the agent what to do."*

ClawWork is a harness you can embed as a library — giving you the batteries-included runtime of products like Claude Code, with the flexibility to build any agent product you want.

## Project Structure

| Package | Description |
|---------|-------------|
| [`libs/clawwork`](libs/clawwork/) | **Core framework** — the agent harness library ([API docs](libs/clawwork/README.md)) |
| [`libs/clawwork_demo`](libs/clawwork_demo/) | **Demo app** — desktop Chat + Cowork built on the framework ([setup guide](libs/clawwork_demo/README.md)) |

```
libs/clawwork/clawwork/
├── computer/       # Computer protocol — local, VM, or cloud (E2B) execution
├── harness/        # Runtime augmentation: environment, permissions, skills, reminders
├── tools/          # Built-in tools: CLI, web, subagents, skills, todos
├── prompts/        # Composable prompt system with Markdown fragments
├── mcp/            # Model Context Protocol client (stdio/sse/http)
├── langchain/      # LangChain/LangGraph integration (isolated — no leakage into core)
└── types.py        # Framework-agnostic types: ToolResult, AgentContext, CLIResult
```

## Design Philosophy

1. **Give the agent a computer** — via the terminal, the way developers work. This is the universal interface for capable agents.
2. **Separate runtime from computer** — the agent should never see its own harness. Isolation by default, convenience by choice.
3. **Vendor-agnostic core** — tools and types have zero LangChain dependency; the integration is isolated in `langchain/`.
4. **Agent-first ergonomics** — tools and results are designed for how agents consume information, not humans.
5. **Protocol-based** — `Computer`, `SubagentRunner`, `SkillCatalog` are pluggable protocols, not concrete classes.
6. **Simplicity** — obvious > clever, testable > convenient, explicit > magical.

Inspired by [Adam Wolff's talk at QCon 2025](https://github.com/wolffiex/qcon-2025-ai-speed) on Claude Code's architecture, and the growing consensus that [the harness — not the model — is what makes agents work](https://www.inngest.com/blog/your-agent-needs-a-harness-not-a-framework).

## Contributing

We welcome contributions! Whether it's new tools, computer implementations, web providers, prompt improvements, or documentation — there's a place for you. See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

[MIT](LICENSE)
