"""Application configuration with config.json persistence."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_config_path() -> Path:
    """Resolve config.json path.

    Uses ``paths.data_dir()`` when ``HEXAGENT_DATA_DIR`` is set (production /
    Electron), otherwise falls back to ``backend/config.json`` next to the
    package for local development convenience.
    """
    from hexagent_api.paths import data_dir

    data = os.environ.get("CLAWWORK_DATA_DIR") or os.environ.get("HEXAGENT_DATA_DIR")
    if data:
        return data_dir() / "config.json"
    return Path(__file__).resolve().parent.parent / "config.json"


CONFIG_PATH = _resolve_config_path()


@dataclass
class ModelConfig:
    id: str = ""
    display_name: str = ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    provider: str = ""
    context_window: int = 0
    supported_modalities: list[str] = field(default_factory=lambda: ["text"])


@dataclass
class AgentConfig:
    id: str = ""
    name: str = ""
    description: str = ""
    system_prompt: str = ""
    tools: list[str] = field(default_factory=list)
    model_id: str = ""  # empty = use default model
    enabled: bool = True


@dataclass
class ToolsConfig:
    search_provider: str = ""  # "tavily" | "brave" | ""
    search_api_key: str = ""
    fetch_provider: str = "jina"  # "jina" | "firecrawl" | ""
    fetch_api_key: str = ""


@dataclass
class SandboxConfig:
    e2b_api_key: str = ""
    chat_enabled: bool = False


@dataclass
class McpServerConfig:
    """MCP server configuration as stored in config.json."""

    id: str = ""
    name: str = ""
    type: str = "http"  # "http" | "stdio"
    url: str = ""
    command: str = ""
    args: str = ""
    env: str = ""  # JSON string of env vars
    headers: str = ""  # JSON string of headers
    enabled: bool = True


@dataclass
class AppConfig:
    models: list[ModelConfig] = field(default_factory=list)
    main_model_id: str = ""
    fast_model_id: str = ""
    agents: list[AgentConfig] = field(default_factory=list)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    disabled_skills: list[str] = field(default_factory=list)
    mcp_servers: list[McpServerConfig] = field(default_factory=list)
    language: str = "en"

    @property
    def main_model(self) -> ModelConfig | None:
        return next((m for m in self.models if m.id == self.main_model_id), None)

    @property
    def fast_model(self) -> ModelConfig | None:
        return next((m for m in self.models if m.id == self.fast_model_id), None)


def load_config() -> AppConfig:
    """Load config from config.json, or return an empty config for first-time setup."""
    file_data: dict[str, Any] = {}
    if CONFIG_PATH.exists():
        try:
            file_data = json.loads(CONFIG_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning("Failed to read %s, starting fresh", CONFIG_PATH)

    if "models" in file_data:
        models = [ModelConfig(**m) for m in file_data["models"]]
        main_id = file_data.get("main_model_id", models[0].id if models else "")
        fast_id = file_data.get("fast_model_id", "")
        agents = [AgentConfig(**a) for a in file_data.get("agents", [])]
        tools = ToolsConfig(**file_data["tools"]) if "tools" in file_data else ToolsConfig()
        sandbox = SandboxConfig(**file_data["sandbox"]) if "sandbox" in file_data else SandboxConfig()
        disabled_skills = file_data.get("disabled_skills", [])
        mcp_servers = [McpServerConfig(**m) for m in file_data.get("mcp_servers", [])]
        language = file_data.get("language", "en")
        return AppConfig(models=models, main_model_id=main_id, fast_model_id=fast_id, agents=agents, tools=tools, sandbox=sandbox, disabled_skills=disabled_skills, mcp_servers=mcp_servers, language=language)

    # No config.json — return empty config (frontend will show setup flow)
    config = AppConfig()
    save_config(config)
    return config


def save_config(config: AppConfig) -> None:
    """Save config to config.json."""
    CONFIG_PATH.write_text(json.dumps(asdict(config), indent=2) + "\n")


def mask_key(key: str) -> str:
    """Mask an API key for display: '****abcd'. Empty keys stay empty."""
    if not key:
        return ""
    if len(key) <= 4:
        return key
    return "****" + key[-4:]


def config_to_dict(config: AppConfig) -> dict[str, Any]:
    """Convert config to dict with masked API keys."""
    d = asdict(config)
    for m in d["models"]:
        m["api_key"] = mask_key(m["api_key"])
    d["tools"]["search_api_key"] = mask_key(d["tools"]["search_api_key"])
    d["tools"]["fetch_api_key"] = mask_key(d["tools"]["fetch_api_key"])
    d["sandbox"]["e2b_api_key"] = mask_key(d["sandbox"]["e2b_api_key"])
    return d
