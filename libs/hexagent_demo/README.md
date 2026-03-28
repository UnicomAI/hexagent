# ClawWork Demo

A ready-to-use desktop application built on [ClawWork](../clawwork/), demonstrating what you can build with an agent harness. This is not a toy example — it's a full-featured Chat + Cowork app that showcases ClawWork's ability to power real products.

> See it as a reference implementation: fork it, restyle it, or use it as the foundation for your own agent product.

## Modes

### Chat Mode

A lightweight, cloud-based mode using [E2B](https://e2b.dev/) sandboxes.

- Shared cloud sandbox for all conversations
- No local infrastructure required — just an E2B API key
- Great for quick tasks, exploration, and demos

### Cowork Mode

A full-featured local mode with per-conversation isolation using [Lima](https://lima-vm.io/) VMs (macOS).

- Each conversation gets its own isolated Linux session
- Mount your local working directories into the VM
- Session persistence across server restarts
- File upload support
- Full filesystem isolation between conversations

## Features

- **Streaming responses** — Real-time SSE streaming with tool execution visualization
- **Rich content rendering** — Markdown, syntax-highlighted code, Mermaid diagrams, ECharts visualizations
- **Document preview** — PDF, Word, PowerPoint, Excel, images
- **Subagent delegation** — Nested agent execution with progress tracking
- **File attachments** — Upload images and documents to conversations
- **MCP integration** — Connect external tool servers dynamically
- **Skill system** — Upload, install, and manage custom agent skills
- **Multi-model support** — Switch between LLM providers per conversation
- **Desktop packaging** — Native Electron app for macOS and Windows

## Architecture

```
clawwork_demo/
├── backend/           # FastAPI backend (Python 3.12+)
│   └── clawwork_api/
│       ├── main.py              # FastAPI app and router registration
│       ├── agent_manager.py     # Agent lifecycle and caching
│       ├── config.py            # Configuration persistence
│       ├── store.py             # In-memory conversation storage
│       └── routes/              # API endpoints
│           ├── chat.py          #   SSE streaming for agent responses
│           ├── conversations.py #   Conversation CRUD + folder browser
│           ├── sessions.py      #   Warm session management (pre-conversation VM setup)
│           ├── config.py        #   Settings persistence + MCP testing
│           ├── skills.py        #   Skill upload, install, enable/disable
│           └── setup.py         #   VM backend detection and provisioning
├── frontend/          # React 19 + TypeScript + Vite
│   └── src/
│       ├── components/          # 30+ React components
│       ├── hooks/               # Custom hooks (useSettings, useThemeMode, etc.)
│       ├── tools/               # Tool result renderers with registry
│       ├── api.ts               # HTTP client + SSE event streaming
│       └── store.ts             # Reducer-based state management
└── electron/          # Electron 33 shell for desktop packaging
```

## Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python package manager)

### Backend

```bash
cd libs/clawwork_demo/backend

# Install dependencies
uv sync

# Run the server
uv run uvicorn clawwork_api.main:app --host 127.0.0.1 --port 8000
```

### Frontend

```bash
cd libs/clawwork_demo/frontend

# Install dependencies
npm install

# Run dev server
npm run dev
```

The frontend runs on `http://localhost:5173` and connects to the backend on port 8000.

### Desktop App (Electron)

```bash
cd libs/clawwork_demo/electron

# Install dependencies
npm install

# Run in development mode
npm run dev
```

## Configuration

On first launch, the app presents an onboarding wizard to configure:

1. **LLM Provider** — API key and model selection (Anthropic, OpenAI, DeepSeek, OpenRouter, etc.)
2. **Web Tools** — Search (Tavily/Brave) and fetch (Jina/Firecrawl) providers
3. **Sandbox** — E2B API key for Chat mode
4. **MCP Servers** — External tool servers (HTTP or stdio)
5. **Skills** — Upload and manage custom agent skills

Configuration is persisted in the platform-specific user data directory:

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/ClawWork/config.json` |
| Windows | `%APPDATA%/ClawWork/config.json` |
| Linux | `~/.config/ClawWork/config.json` |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `CLAWWORK_DATA_DIR` | Override user data directory |
| `E2B_API_KEY` | E2B sandbox API key (Chat mode) |
| `HOST` | Backend host (default: `127.0.0.1`) |
| `PORT` | Backend port (default: `8000`) |

## API Endpoints

### Chat
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat/{id}/message` | Stream agent response (SSE) |
| `POST` | `/api/chat/{id}/upload` | Upload file attachment |

### Conversations
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/conversations` | List all conversations |
| `POST` | `/api/conversations` | Create new conversation |
| `GET` | `/api/conversations/{id}` | Get conversation with messages |
| `PATCH` | `/api/conversations/{id}` | Update title/model/working_dir |
| `DELETE` | `/api/conversations/{id}` | Delete conversation |

### Configuration
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/config` | Get config (API keys masked) |
| `PUT` | `/api/config` | Update and persist config |
| `POST` | `/api/config/mcp-test` | Test MCP server connection |

### Skills
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/skills` | List all skills |
| `POST` | `/api/skills/upload` | Upload skill archive (.zip) |
| `POST` | `/api/skills/{name}/install` | Install example skill |
| `PUT` | `/api/skills/{name}/toggle` | Enable/disable skill |
| `DELETE` | `/api/skills/{name}` | Delete skill |

### VM Setup (Cowork mode)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/setup/vm` | Check VM backend + instance status |
| `POST` | `/api/setup/vm/install` | Install Lima (SSE progress) |
| `POST` | `/api/setup/vm/build` | Create/start VM (SSE progress) |
| `POST` | `/api/setup/vm/provision` | Provision VM with dependencies |

## Using as a Starting Point

The demo is designed to be forked and customized. Key extension points:

- **New modes** — Add operating modes beyond Chat and Cowork (e.g., autonomous batch processing)
- **Custom tools** — Register your own `BaseAgentTool` instances via `extra_tools` in the agent config
- **Branding** — The frontend is standard React/TypeScript — restyle to match your product
- **Deployment** — The backend is a standard FastAPI app that can be deployed anywhere

## Building for Distribution

### Package the backend

```bash
cd libs/clawwork_demo/backend
pyinstaller --name clawwork_api_server ...  # Creates standalone binary
```

### Build the desktop app

```bash
cd libs/clawwork_demo/electron

# macOS
npm run build:mac           # ARM64
npm run build:mac-x64       # Intel
npm run build:mac-universal # Universal

# Windows
npm run build:win           # x64
npm run build:win-arm64     # ARM64
```
