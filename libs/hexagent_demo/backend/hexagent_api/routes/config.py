"""Config API endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter

from hexagent_api.agent_manager import agent_manager
from hexagent_api.config import (
    AgentConfig,
    AppConfig,
    McpServerConfig,
    ModelConfig,
    SandboxConfig,
    ToolsConfig,
    config_to_dict,
    load_config,
    save_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
async def get_config() -> dict[str, Any]:
    """Return current config with masked API keys."""
    return config_to_dict(load_config())


@router.put("")
async def put_config(body: dict[str, Any]) -> dict[str, Any]:
    """Update config, save to disk, and restart the agent."""
    current = load_config()

    if "models" in body:
        # Build a lookup of existing models to preserve unmasked api_keys
        existing_by_id = {m.id: m for m in current.models}
        new_models: list[ModelConfig] = []
        for m_data in body["models"]:
            # If api_key is masked, keep existing value
            if m_data.get("api_key", "").startswith("****"):
                old = existing_by_id.get(m_data.get("id", ""))
                if old:
                    m_data["api_key"] = old.api_key
                else:
                    m_data["api_key"] = ""
            # Coerce context_window
            cw = m_data.get("context_window", 0)
            m_data["context_window"] = int(cw) if cw else 0
            new_models.append(ModelConfig(**m_data))
        current.models = new_models

    if "main_model_id" in body:
        current.main_model_id = body["main_model_id"]
    if "fast_model_id" in body:
        current.fast_model_id = body["fast_model_id"]

    if "agents" in body:
        current.agents = [AgentConfig(**a) for a in body["agents"]]

    if "tools" in body:
        t = body["tools"]
        # Preserve unmasked API keys
        if t.get("search_api_key", "").startswith("****"):
            t["search_api_key"] = current.tools.search_api_key
        if t.get("fetch_api_key", "").startswith("****"):
            t["fetch_api_key"] = current.tools.fetch_api_key
        current.tools = ToolsConfig(**t)

    if "sandbox" in body:
        s = body["sandbox"]
        if s.get("e2b_api_key", "").startswith("****"):
            s["e2b_api_key"] = current.sandbox.e2b_api_key
        current.sandbox = SandboxConfig(**s)

    if "mcp_servers" in body:
        current.mcp_servers = [McpServerConfig(**m) for m in body["mcp_servers"]]

    if "language" in body:
        current.language = body["language"]

    save_config(current)

    # Invalidate cached agents so they pick up new config on next use
    logger.info("Config updated, invalidating agent cache...")
    await agent_manager.invalidate_cache()
    logger.info("Agent cache cleared. Agents will be recreated on next request.")

    return config_to_dict(current)


@router.post("/mcp-test")
async def test_mcp_connection(body: dict[str, Any]) -> dict[str, Any]:
    """Test an MCP server connection without saving config.

    Accepts the same shape as a single McpServer entry from the frontend.
    Returns { ok: true, tools: int } on success or { ok: false, error: str }.
    """
    from hexagent.mcp._client import McpClient

    server_type = body.get("type", "http")
    name = body.get("name", "test")

    # Build runtime config dict matching McpServerConfig TypedDict
    if server_type == "http":
        cfg: dict[str, Any] = {"type": "http", "url": body.get("url", "")}
        headers = body.get("headers", "")
        if headers:
            cfg["headers"] = json.loads(headers) if isinstance(headers, str) else headers
    else:
        cfg = {"type": "stdio", "command": body.get("command", "")}
        args = body.get("args", "")
        if args:
            cfg["args"] = args if isinstance(args, list) else args.split()
        env = body.get("env", "")
        if env:
            cfg["env"] = json.loads(env) if isinstance(env, str) else env

    client = McpClient(name, cfg)
    try:
        async with asyncio.timeout(15):
            async with client:
                tool_count = len(client.tools)
        return {"ok": True, "tools": tool_count}
    except Exception as exc:
        # Extract the most useful error message
        msg = str(exc)
        if hasattr(exc, "__cause__") and exc.__cause__:
            msg = str(exc.__cause__)
        return {"ok": False, "error": msg}
