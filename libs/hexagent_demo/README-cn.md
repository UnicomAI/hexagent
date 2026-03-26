# HexAgent 演示

一个基于 [HexAgent](../hexagent/) 构建的即用型桌面应用程序，展示了你可以使用智能体（Agent）框架构建什么。这不仅仅是一个简单的示例——它是一个全功能的聊天 + 协作（Chat + Cowork）应用，展示了 HexAgent 驱动真实产品的能力。

> 将其视为参考实现：你可以 fork 它、重新设计样式，或者将其作为你自己的智能体产品的基础。

## 模式

### 聊天模式 (Chat Mode)

一个使用 [E2B](https://e2b.dev/) 沙箱的轻量级、基于云端的模式。

- 所有对话共享同一个云端沙箱
- 无需本地基础设施——只需一个 E2B API 密钥
- 非常适合快速任务、探索和演示

### 协作模式 (Cowork Mode)

一个全功能的本地模式，使用 [Lima](https://lima-vm.io/) 虚拟机 (macOS) 实现每个对话的隔离。

- 每个对话都有自己独立的 Linux 会话
- 将你的本地工作目录挂载到虚拟机中
- 服务器重启后会话仍可持久化
- 支持文件上传
- 不同对话之间完全的文件系统隔离

## 功能特性

- **流式响应** —— 带有工具执行可视化的实时 SSE 流式传输
- **丰富的内渲染** —— 支持 Markdown、语法高亮代码、Mermaid 图表、ECharts 可视化
- **文档预览** —— 支持 PDF、Word、PowerPoint、Excel、图片预览
- **子智能体委派** —— 带有进度跟踪的嵌套智能体执行
- **文件附件** —— 向对话上传图片和文档
- **MCP 集成** —— 动态连接外部工具服务器
- **技能系统** —— 上传、安装和管理自定义智能体技能
- **多模型支持** —— 每个对话可切换不同的 LLM 提供商
- **桌面端打包** —— 适用于 macOS 和 Windows 的原生 Electron 应用

## 架构

```
hexagent_demo/
├── backend/           # FastAPI 后端 (Python 3.12+)
│   └── hexagent_api/
│       ├── main.py              # FastAPI 应用和路由注册
│       ├── agent_manager.py     # 智能体生命周期和缓存
│       ├── config.py            # 配置持久化
│       ├── store.py             # 内存中的对话存储
│       └── routes/              # API 接口
│           ├── chat.py          #   用于智能体响应的 SSE 流
│           ├── conversations.py #   对话 CRUD + 文件夹浏览器
│           ├── sessions.py      #   预热会话管理 (对话前的虚拟机设置)
│           ├── config.py        #   设置持久化 + MCP 测试
│           ├── skills.py        #   技能上传、安装、启用/禁用
│           └── setup.py         #   虚拟机后端检测和配置
├── frontend/          # React 19 + TypeScript + Vite
│   └── src/
│       ├── components/          # 30 多个 React 组件
│       ├── hooks/               # 自定义 Hooks (useSettings, useThemeMode 等)
│       ├── tools/               # 带注册表的工具结果渲染器
│       ├── api.ts               # HTTP 客户端 + SSE 事件流
│       └── store.ts             # 基于 Reducer 的状态管理
└── electron/          # 用于桌面打包的 Electron 33 外壳
```

## 设置

### 前置条件

- Python 3.12+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) (Python 包管理器)

### 后端

```bash
cd libs/hexagent_demo/backend

# 安装依赖
uv sync

# 运行服务器
uv run uvicorn hexagent_api.main:app --host 127.0.0.1 --port 8000
```

### 前端

```bash
cd libs/hexagent_demo/frontend

# 安装依赖
npm install

# 运行开发服务器
npm run dev
```

前端运行在 `http://localhost:5173` 并连接到 8000 端口的后端。

### 桌面应用 (Electron)

```bash
cd libs/hexagent_demo/electron

# 安装依赖
npm install

# 在开发模式下运行
npm run dev
```

## 配置

在首次启动时，应用会显示一个引导向导来配置：

1. **LLM 提供商** —— API 密钥和模型选择 (Anthropic, OpenAI, DeepSeek, OpenRouter 等)
2. **网络工具** —— 搜索 (Tavily/Brave) 和抓取 (Jina/Firecrawl) 提供商
3. **沙箱** —— 用于聊天模式的 E2B API 密钥
4. **MCP 服务器** —— 外部工具服务器 (HTTP 或 stdio)
5. **技能** —— 上传和管理自定义智能体技能

配置持久化在平台特定的用户数据目录中：

| 平台 | 路径 |
|----------|------|
| macOS | `~/Library/Application Support/HexAgent/config.json` |
| Windows | `%APPDATA%/HexAgent/config.json` |
| Linux | `~/.config/HexAgent/config.json` |

## 环境变量

| 变量 | 描述 |
|----------|-------------|
| `HEXAGENT_DATA_DIR` | 覆盖用户数据目录 |
| `E2B_API_KEY` | E2B 沙箱 API 密钥 (聊天模式) |
| `HOST` | 后端主机 (默认: `127.0.0.1`) |
| `PORT` | 后端端口 (默认: `8000`) |

## API 接口

### 聊天 (Chat)
| 方法 | 路径 | 描述 |
|--------|------|-------------|
| `POST` | `/api/chat/{id}/message` | 流式传输智能体响应 (SSE) |
| `POST` | `/api/chat/{id}/upload` | 上传文件附件 |

### 对话 (Conversations)
| 方法 | 路径 | 描述 |
|--------|------|-------------|
| `GET` | `/api/conversations` | 列出所有对话 |
| `POST` | `/api/conversations` | 创建新对话 |
| `GET` | `/api/conversations/{id}` | 获取带有消息内容的对话 |
| `PATCH` | `/api/conversations/{id}` | 更新标题/模型/工作目录 |
| `DELETE` | `/api/conversations/{id}` | 删除对话 |

### 配置 (Configuration)
| 方法 | 路径 | 描述 |
|--------|------|-------------|
| `GET` | `/api/config` | 获取配置 (API 密钥已脱敏) |
| `PUT` | `/api/config` | 更新并持久化配置 |
| `POST` | `/api/config/mcp-test` | 测试 MCP 服务器连接 |

### 技能 (Skills)
| 方法 | 路径 | 描述 |
|--------|------|-------------|
| `GET` | `/api/skills` | 列出所有技能 |
| `POST` | `/api/skills/upload` | 上传技能归档文件 (.zip) |
| `POST` | `/api/skills/{name}/install` | 安装示例技能 |
| `PUT` | `/api/skills/{name}/toggle` | 启用/禁用技能 |
| `DELETE` | `/api/skills/{name}` | 删除技能 |

### 虚拟机设置 (VM Setup - 协作模式)
| 方法 | 路径 | 描述 |
|--------|------|-------------|
| `GET` | `/api/setup/vm` | 检查虚拟机后端 + 实例状态 |
| `POST` | `/api/setup/vm/install` | 安装 Lima (SSE 进度) |
| `POST` | `/api/setup/vm/build` | 创建/启动虚拟机 (SSE 进度) |
| `POST` | `/api/setup/vm/provision` | 为虚拟机配置依赖项 |

## 作为起点使用

该演示项目旨在被 fork 和自定义。关键扩展点：

- **新模式** —— 添加聊天和协作之外的操作模式 (例如：自主批处理)
- **自定义工具** —— 通过智能体配置中的 `extra_tools` 注册你自己的 `BaseAgentTool` 实例
- **品牌定制** —— 前端是标准的 React/TypeScript —— 可重新设计样式以匹配你的产品
- **部署** —— 后端是一个标准的 FastAPI 应用，可以部署在任何地方

## 构建与分发

### 打包后端

```bash
cd libs/hexagent_demo/backend
pyinstaller --name hexagent_api_server ...  # 创建独立的可执行二进制文件
```

### 构建桌面应用

```bash
cd libs/hexagent_demo/electron

# macOS
npm run build:mac           # ARM64
npm run build:mac-x64       # Intel
npm run build:mac-universal # 通用版本

# Windows
npm run build:win           # x64
npm run build:win-arm64     # ARM64
```
