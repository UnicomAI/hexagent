"""Agent lifecycle management.

Singleton that manages the OpenAgent agent lifecycle.

- **Chat mode**: one shared ``RemoteE2BComputer`` for all conversations.
- **Cowork mode**: each conversation gets its own session computer
  (isolated Linux user on the shared Lima VM).  Sessions are identified by
  ``session_name`` and can be resumed across server restarts.

Agents are cached by ``(model_id, session_key)`` where *session_key* is
``"chat"`` for chat mode or the VM ``session_name`` for cowork mode.

``start()`` boots the VM and mounts skill directories so they are ready
before the first conversation.  Agents are created lazily on first request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages the OpenAgent agent lifecycle with per-session caching.

    There is no global "current agent" state.  Every public method receives
    explicit ``model_id``, ``mode``, and ``session_name`` parameters so that
    concurrent requests never interfere with each other.
    """

    def __init__(self) -> None:
        # "chat" -> shared chat computer, session_name -> per-conversation cowork computer
        self._computers: dict[str, Any] = {}
        # (model_id, session_key) -> agent   where session_key = "chat" | session_name
        self._agents: dict[tuple[str, str], Any] = {}
        self._mcp_servers: dict[str, Any] | None = None
        self._vm_manager: Any | None = None
        self._conv_locks: dict[str, asyncio.Lock] = {}
        self._setup_lock = asyncio.Lock()
        # session_name -> (working_dir_source, mount_target)
        self._session_working_dirs: dict[str, tuple[str, str]] = {}

    def conversation_lock(self, conversation_id: str) -> asyncio.Lock:
        """Per-conversation lock to serialise prepare/send/mount operations."""
        if conversation_id not in self._conv_locks:
            self._conv_locks[conversation_id] = asyncio.Lock()
        return self._conv_locks[conversation_id]

    # ── Computer management ──

    async def _ensure_computer(
        self,
        mode: str,
        session_name: str | None = None,
        working_dir: str | None = None,
    ) -> tuple[Any, str]:
        """Start or resume a computer for the given mode/session.

        Returns:
            (computer, session_key) where session_key is ``"chat"`` or the
            VM session name.
        """
        if mode == "chat":
            if "chat" in self._computers:
                return self._computers["chat"], "chat"

            async with self._setup_lock:
                if "chat" in self._computers:
                    return self._computers["chat"], "chat"

                from openagent_api.config import load_config

                cfg = load_config()
                e2b_key = cfg.sandbox.e2b_api_key
                if e2b_key:
                    os.environ["E2B_API_KEY"] = e2b_key

                from openagent.computer.remote.e2b import RemoteE2BComputer

                logger.info("Starting RemoteE2BComputer for chat mode...")
                computer = RemoteE2BComputer()
                await computer.start()
                self._computers["chat"] = computer
                return computer, "chat"

        # Cowork mode — per-conversation session
        if session_name and session_name in self._computers:
            return self._computers[session_name], session_name

        async with self._setup_lock:
            # Re-check after acquiring lock (another coroutine may have created it)
            if session_name and session_name in self._computers:
                return self._computers[session_name], session_name

            # Lazy-create LocalVM
            if self._vm_manager is None:
                await self._ensure_vm_manager()

            if session_name:
                logger.info("Resuming session: %s", session_name)
                computer = await self._vm_manager.computer(resume=session_name)
            else:
                from pathlib import Path

                from openagent.computer import Mount

                session_mounts: list[Mount] | None = None
                if working_dir:
                    session_mounts = [Mount(source=working_dir, target=Path(working_dir).name, writable=True)]
                logger.info("Creating new session (mounts=%s)...", session_mounts)
                computer = await self._vm_manager.computer(mounts=session_mounts)

            actual_name = computer.session_name
            self._computers[actual_name] = computer
            logger.info("Session ready: %s", actual_name)
            return computer, actual_name

    # ── MCP servers ──

    def _get_mcp_servers(self) -> dict[str, Any]:
        """Return MCP server configs built from config.json (rebuilt on each call
        after cache invalidation so config changes take effect)."""
        if self._mcp_servers is None:
            from openagent_api.config import load_config

            servers: dict[str, Any] = {}
            for mcp in load_config().mcp_servers:
                if not mcp.enabled or not mcp.name:
                    continue
                if mcp.type == "http":
                    cfg: dict[str, Any] = {"type": "http", "url": mcp.url}
                    if mcp.headers:
                        cfg["headers"] = json.loads(mcp.headers) if isinstance(mcp.headers, str) else mcp.headers
                    servers[mcp.name] = cfg
                elif mcp.type == "stdio":
                    cfg = {"type": "stdio", "command": mcp.command}
                    if mcp.args:
                        cfg["args"] = mcp.args if isinstance(mcp.args, list) else mcp.args.split()
                    if mcp.env:
                        cfg["env"] = json.loads(mcp.env) if isinstance(mcp.env, str) else mcp.env
                    servers[mcp.name] = cfg
            self._mcp_servers = servers
        return self._mcp_servers

    # ── Agent management ──

    async def _get_or_create_agent(
        self,
        model_id: str,
        mode: str,
        session_name: str | None = None,
        working_dir: str | None = None,
    ) -> tuple[Any, str]:
        """Get a cached agent or create one.

        Returns:
            (agent, session_key) — the session_key is needed so callers can
            store the session_name on the conversation when it's new.
        """
        computer, session_key = await self._ensure_computer(mode, session_name, working_dir=working_dir)

        cache_key = (model_id, session_key)
        if cache_key in self._agents:
            return self._agents[cache_key], session_key

        from dotenv import load_dotenv

        load_dotenv()

        from langchain_anthropic import ChatAnthropic
        from langchain_deepseek import ChatDeepSeek
        from langchain_openai import ChatOpenAI
        from openagent import create_agent
        from openagent.computer.base import SESSION_OUTPUTS_DIR
        from openagent.harness.definition import AgentDefinition
        from openagent.harness.model import ModelProfile
        from openagent.tools import PresentToUserTool
        from openagent.tools.web import (
            BraveSearchProvider,
            FetchProvider,
            FirecrawlFetchProvider,
            JinaFetchProvider,
            SearchProvider,
            TavilySearchProvider,
        )

        from openagent_api.config import load_config

        cfg = load_config()
        target = next((m for m in cfg.models if m.id == model_id), None)
        if not target:
            msg = f"Model config not found: {model_id}"
            raise RuntimeError(msg)

        fast_cfg = cfg.fast_model or target

        def _make_chat_model(mc: Any) -> Any:
            if mc.provider == "anthropic":
                return ChatAnthropic(
                    model=mc.model,
                    api_key=mc.api_key,
                    base_url=mc.base_url,
                )
            if mc.provider == "deepseek":
                return ChatDeepSeek(
                    model=mc.model,
                    api_key=mc.api_key,
                    api_base=mc.base_url,
                )
            # Default: openai
            return ChatOpenAI(
                model=mc.model,
                api_key=mc.api_key,
                base_url=mc.base_url,
            )

        main_model = ModelProfile(
            model=_make_chat_model(target),
            context_window=target.context_window,
        )

        fast_model = ModelProfile(
            model=_make_chat_model(fast_cfg),
            context_window=fast_cfg.context_window,
        )

        # Build agent definitions from config
        agent_defs: dict[str, AgentDefinition] = {}
        for ac in cfg.agents:
            if not ac.enabled or not ac.name:
                continue
            agent_defs[ac.name] = AgentDefinition(
                description=ac.description,
                system_prompt=ac.system_prompt,
                tools=tuple(ac.tools) if ac.tools else (),
            )

        # Build web tool providers from config
        tc = cfg.tools
        search: SearchProvider | None = None
        if tc.search_provider == "tavily":
            search = TavilySearchProvider(api_key=tc.search_api_key or None)
        elif tc.search_provider == "brave":
            search = BraveSearchProvider(api_key=tc.search_api_key or None)

        fetch: FetchProvider | None = None
        if tc.fetch_provider == "jina":
            fetch = JinaFetchProvider(api_key=tc.fetch_api_key or None)
        elif tc.fetch_provider == "firecrawl":
            fetch = FirecrawlFetchProvider(api_key=tc.fetch_api_key or None)

        logger.info(
            "Creating agent for model=%s (%s) session=%s",
            target.display_name, target.model, session_key,
        )
        # Cowork sessions have skills mounted at /mnt/skills/{public,user}
        skill_paths = ("/mnt/skills/public", "/mnt/skills/user") if mode != "chat" else ()

        # PresentToUserTool output directory depends on mode
        if session_key == "chat":
            output_dir = f"/{SESSION_OUTPUTS_DIR}"
        else:
            output_dir = f"/sessions/{session_key}/{SESSION_OUTPUTS_DIR}"

        agent = await create_agent(
            model=main_model,
            computer=computer,
            fast_model=fast_model,
            mcp_servers=self._get_mcp_servers(),
            agents=agent_defs or None,
            search_provider=search,
            fetch_provider=fetch,
            skill_paths=skill_paths,
            extra_tools=[PresentToUserTool(computer=computer, output_dir=output_dir)],
        )
        self._agents[cache_key] = agent
        logger.info("create_agent() returned: %r", agent)
        logger.info(
            "Agent ready for model=%s (%s) session=%s",
            target.display_name, target.model, session_key,
        )
        return agent, session_key

    # ── Public API ──

    async def _ensure_vm_manager(self) -> None:
        """Create LocalVM and mount skills if not already running."""
        if self._vm_manager is not None:
            return

        async with self._setup_lock:
            if self._vm_manager is not None:
                return

            from openagent.computer.local import LocalVM

            vm = LocalVM()
            await vm.start()
            self._vm_manager = vm
            await self._mount_skills()

    async def _mount_skills(self) -> None:
        """Mount skill directories (public + user) into the VM."""
        assert self._vm_manager is not None
        from pathlib import Path

        from openagent.computer import Mount

        existing_guests = {m.guest_path for m in self._vm_manager.list_mounts()}

        skills_base = Path(__file__).resolve().parent.parent / "skills"
        skill_mounts: list[Mount] = []
        for subdir in ("public", "user"):
            skills_dir = skills_base / subdir
            if skills_dir.is_dir():
                guest = f"/mnt/skills/{subdir}"
                if guest not in existing_guests:
                    skill_mounts.append(
                        Mount(source=str(skills_dir), target=f"skills/{subdir}")
                    )
        if skill_mounts:
            logger.info("Mounting %d skill dir(s): %s", len(skill_mounts), [m.target for m in skill_mounts])
            await self._vm_manager.mount(skill_mounts)

    async def start(self) -> None:
        """Initialize the agent manager.

        Starts the VM and mounts skill directories so they are ready
        before the first conversation.
        """
        from dotenv import load_dotenv

        load_dotenv()
        await self._ensure_vm_manager()
        logger.info("Agent manager initialized.")

    async def ensure_agent(
        self,
        model_id: str,
        mode: str = "chat",
        session_name: str | None = None,
        working_dir: str | None = None,
    ) -> str | None:
        """Ensure an agent is available for the specified model/mode/session.

        Returns:
            The VM session_name for cowork mode (useful when a new session was
            created), or ``None`` for chat mode.
        """
        _, session_key = await self._get_or_create_agent(
            model_id, mode, session_name, working_dir=working_dir,
        )
        return session_key if session_key != "chat" else None

    async def stream_response(
        self,
        input_dict: dict[str, Any],
        conversation_id: str,
        model_id: str,
        mode: str = "chat",
        session_name: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream agent response events via astream_events.

        The agent is resolved from the cache using the explicit parameters.
        It must have been created by a prior ``ensure_agent()`` call.

        Args:
            input_dict: The input dict with ``messages`` key.
            conversation_id: Used as LangGraph ``thread_id`` for persistence.
            model_id: Model to use for this request.
            mode: Conversation mode ('chat' or 'cowork').
            session_name: VM session name (cowork only).

        Yields:
            LangGraph v2 event dicts.
        """
        agent, _ = await self._get_or_create_agent(model_id, mode, session_name)
        config = {"configurable": {"thread_id": conversation_id}, "recursion_limit": 10_000}
        async for event in agent.astream_events(input_dict, config=config):
            yield event

    async def stop(self) -> None:
        """Shut down all agents and computers."""
        for key, agent in self._agents.items():
            logger.info("Closing agent for %s...", key)
            await agent.aclose()
        self._agents.clear()
        # Stop chat-mode computers individually
        for key, computer in self._computers.items():
            if key == "chat":
                logger.info("Stopping computer %s...", key)
                await computer.stop()
        self._computers.clear()
        # Stop the shared LocalVM
        if self._vm_manager is not None:
            logger.info("Stopping LocalVM...")
            await self._vm_manager.stop()
            self._vm_manager = None
        self._mcp_servers = None
        logger.info("Shutdown complete.")

    async def ensure_session(
        self,
        mode: str,
        session_name: str | None = None,
        working_dir: str | None = None,
    ) -> str | None:
        """Boot the computer/session without creating an agent.

        Returns the session_name for cowork mode, None for chat.
        """
        _, session_key = await self._ensure_computer(mode, session_name, working_dir=working_dir)
        return session_key if session_key != "chat" else None

    async def mount_working_dir(self, session_name: str, working_dir: str) -> None:
        """Mount a working directory into an existing cowork session.

        If a different working directory was previously mounted for this
        session, it is unmounted first.
        """
        if self._vm_manager is None:
            return
        from pathlib import Path

        from openagent.computer import Mount

        new_target = Path(working_dir).name

        import shlex

        # Unmount previous working dir if switching to a different one
        prev = self._session_working_dirs.get(session_name)
        prev_guest_path: str | None = None
        if prev is not None:
            prev_source, prev_target = prev
            if prev_source == working_dir:
                return  # Same dir already mounted
            prev_guest_path = f"/sessions/{session_name}/mnt/{prev_target}"

            # Force-unmount inside the guest BEFORE the VM restart to flush
            # FUSE/SSHFS state.  Without this, Lima's mount driver can leave
            # stale data on the old mount point after a single restart cycle.
            result = await self._vm_manager._vm.shell(
                f"sudo umount {shlex.quote(prev_guest_path)} 2>/dev/null; true"
            )
            if result.exit_code != 0:
                logger.warning(
                    "Guest umount %s failed (exit_code=%d): %s",
                    prev_guest_path, result.exit_code, result.stderr or result.stdout,
                )

            await self._vm_manager.unmount(prev_target, session=session_name, defer=True)
            logger.info("Unmounted (deferred) %s for session %s", prev_source, session_name)

        # mount() with defer=False applies all pending changes in a single restart
        mount = Mount(source=working_dir, target=new_target, writable=True)
        await self._vm_manager.mount([mount], session=session_name)
        self._session_working_dirs[session_name] = (working_dir, new_target)
        logger.info("Mounted working dir %s for session %s", working_dir, session_name)

        # Remove the stale mount-point directory left behind after unmount.
        # The dir may still be a FUSE mount point briefly after restart, so
        # attempt umount before rmdir.
        if prev_guest_path is not None:
            quoted = shlex.quote(prev_guest_path)
            result = await self._vm_manager._vm.shell(
                f"sudo umount {quoted} 2>/dev/null; sudo rmdir {quoted}"
            )
            if result.exit_code != 0:
                logger.warning(
                    "Could not remove stale mount point %s (exit_code=%d): %s",
                    prev_guest_path, result.exit_code, result.stderr or result.stdout,
                )

    async def teardown_session(self, mode: str, session_name: str | None = None) -> None:
        """Tear down a computer session and any cached agents for it."""
        if mode == "chat":
            return  # Don't tear down the shared chat computer
        if not session_name or session_name not in self._computers:
            return
        computer = self._computers.pop(session_name)
        # Remove any agents cached for this session
        keys_to_remove = [k for k in self._agents if k[1] == session_name]
        for key in keys_to_remove:
            agent = self._agents.pop(key)
            await agent.aclose()
            logger.info("Closed agent for %s", key)
        await computer.stop()
        logger.info("Torn down session: %s", session_name)

    def get_computer(self, mode: str, session_name: str | None = None) -> Any | None:
        """Get the computer instance for a given mode/session, or None."""
        if mode == "chat":
            return self._computers.get("chat")
        if session_name:
            return self._computers.get(session_name)
        return None

    async def invalidate_cache(self) -> None:
        """Close all cached agents (e.g. after config change). Computers stay."""
        self._mcp_servers = None  # Rebuild from config on next agent creation
        for key, agent in self._agents.items():
            logger.info("Closing cached agent for %s...", key)
            try:
                await agent.aclose()
            except RuntimeError:
                logger.warning(
                    "Could not cleanly close agent for %s (cross-task scope), discarding",
                    key,
                )
        self._agents.clear()


# Module-level singleton
agent_manager = AgentManager()
