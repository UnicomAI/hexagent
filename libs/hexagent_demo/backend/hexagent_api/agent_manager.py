"""Agent lifecycle management.

Singleton that manages the HexAgent agent lifecycle.

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
import shlex
import sys
from typing import Any

from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages the HexAgent agent lifecycle with per-session caching.

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
        # Per-cache-key locks to prevent duplicate agent creation
        self._agent_locks: dict[tuple[str, str], asyncio.Lock] = {}
        # Global skill resolver for the VM (initialized in start)
        self._skill_resolver: Any | None = None
        # session_name -> (working_dir_source, mount_target)
        self._session_working_dirs: dict[str, tuple[str, str]] = {}
        # Background warm-up task: auto-start VM manager after app startup.
        self._vm_warm_task: asyncio.Task[None] | None = None

    def conversation_lock(self, conversation_id: str) -> asyncio.Lock:
        """Per-conversation lock to serialise prepare/send/mount operations."""
        if conversation_id not in self._conv_locks:
            self._conv_locks[conversation_id] = asyncio.Lock()
        return self._conv_locks[conversation_id]

    @staticmethod
    def _set_computer_default_cwd(computer: Any, cwd: str | None) -> None:
        """Best-effort hook for session computers that support default cwd."""
        setter = getattr(computer, "set_default_cwd", None)
        if callable(setter):
            setter(cwd)

    async def _verify_session_dir_writable(self, session_name: str, guest_dir: str) -> None:
        """Ensure the cowork session user can write to the selected working dir."""
        if self._vm_manager is None:
            return
        vm = getattr(self._vm_manager, "_vm", None)
        if vm is None:
            return

        probe = f"{guest_dir.rstrip('/')}/.hexagent_write_probe_{os.getpid()}"
        cmd = (
            f"test -d {shlex.quote(guest_dir)} && "
            f"test -w {shlex.quote(guest_dir)} && "
            f"touch {shlex.quote(probe)} && "
            f"rm -f {shlex.quote(probe)}"
        )
        result = await vm.shell(cmd, user=session_name)
        if result.exit_code == 0:
            return

        detail = (result.stderr or result.stdout or "").strip() or "unknown error"
        raise RuntimeError(
            "Selected working directory is mounted but not writable for the cowork session user. "
            f"guest_dir={guest_dir} session={session_name} detail={detail}. "
            "Please choose a writable local folder, "
            "or adjust Windows folder ACL/WSL mount permissions."
        )

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

                from hexagent_api.config import load_config

                cfg = load_config()
                e2b_key = cfg.sandbox.e2b_api_key or os.environ.get("E2B_API_KEY", "")
                if not e2b_key:
                    raise RuntimeError(
                        "E2B API key not configured. "
                        "Please set it in Settings > Sandbox."
                    )
                os.environ["E2B_API_KEY"] = e2b_key

                from hexagent.computer.remote.e2b import RemoteE2BComputer

                logger.info("Starting RemoteE2BComputer for chat mode...")
                computer = RemoteE2BComputer(template="an7tang/hexagent")
                try:
                    await asyncio.wait_for(computer.start(), timeout=30)
                except asyncio.TimeoutError:
                    raise RuntimeError(
                        "E2B sandbox creation timed out after 30s. "
                        "Check your network connection and E2B API key."
                    )
                self._computers["chat"] = computer
                return computer, "chat"

        # Cowork mode — per-conversation session
        if session_name and session_name in self._computers:
            return self._computers[session_name], session_name

        # Ensure VM manager is ready BEFORE acquiring the setup lock.
        # _ensure_vm_manager() uses the same _setup_lock internally;
        # calling it while already holding the lock would deadlock
        # (asyncio.Lock is not reentrant).
        if self._vm_manager is None:
            import shutil

            if sys.platform == "win32":
                from hexagent.computer.local._wsl import _resolve_wsl_exe

                vm_backend_ready = _resolve_wsl_exe() is not None
            else:
                vm_backend_ready = bool(shutil.which("limactl"))
            if not vm_backend_ready:
                raise RuntimeError(
                    "Cowork mode requires VM setup. "
                    "Please install and configure it in Settings \u2192 Sandbox."
                )
            await self._ensure_vm_manager()

        async with self._setup_lock:
            # Re-check after acquiring lock (another coroutine may have created it)
            if session_name and session_name in self._computers:
                return self._computers[session_name], session_name

            try:
                if session_name:
                    logger.info("Resuming session: %s", session_name)
                    computer = await self._vm_manager.computer(resume=session_name)
                else:
                    from pathlib import Path

                    from hexagent.computer import Mount

                    session_mounts: list[Mount] | None = None
                    default_cwd: str | None = None
                    if working_dir:
                        mount_target = Path(working_dir).name
                        session_mounts = [Mount(source=working_dir, target=mount_target, writable=True)]
                        default_cwd = f"/sessions/{{session}}/mnt/{mount_target}"
                    logger.info("Creating new session (mounts=%s)...", session_mounts)
                    computer = await self._vm_manager.computer(mounts=session_mounts)
                    if default_cwd is not None:
                        resolved_cwd = default_cwd.format(session=computer.session_name)
                        self._set_computer_default_cwd(computer, resolved_cwd)
                        await self._verify_session_dir_writable(computer.session_name, resolved_cwd)
            except FileNotFoundError:
                raise RuntimeError(
                    "Cowork mode requires VM setup. "
                    "Please install and configure it in Settings \u2192 Sandbox."
                ) from None
            except Exception as exc:
                # Preserve actionable details instead of collapsing all errors
                # into "VM is not running", which can hide the real cause.
                detail = str(exc).strip() or exc.__class__.__name__
                low = detail.lower()
                if "does not exist" in low and "wsl distro" in low:
                    raise RuntimeError(
                        "Cowork mode requires VM setup. "
                        "Please install and configure it in Settings \u2192 Sandbox."
                    ) from None
                if "not running" in low and "session" not in low:
                    raise RuntimeError(
                        "VM is not running. "
                        "Please set it up in Settings \u2192 Sandbox."
                    ) from None
                raise RuntimeError(f"Cowork session setup failed: {detail}") from exc

            actual_name = computer.session_name
            self._computers[actual_name] = computer
            logger.info("Session ready: %s", actual_name)
            return computer, actual_name

    # ── MCP servers ──

    def _get_mcp_servers(self) -> dict[str, Any]:
        """Return MCP server configs built from config.json (rebuilt on each call
        after cache invalidation so config changes take effect)."""
        if self._mcp_servers is None:
            from hexagent_api.config import load_config

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

        # Acquire a per-key lock to prevent duplicate agent creation when
        # _warm_agent() and the chat route race on the same session.
        if cache_key not in self._agent_locks:
            self._agent_locks[cache_key] = asyncio.Lock()
        async with self._agent_locks[cache_key]:
            # Re-check after acquiring lock — another caller may have created it
            if cache_key in self._agents:
                return self._agents[cache_key], session_key

            from dotenv import load_dotenv

            load_dotenv()

            from langchain_anthropic import ChatAnthropic
            from langchain_deepseek import ChatDeepSeek
            from langchain_openai import ChatOpenAI
            from hexagent import create_agent
            from hexagent.computer.base import SESSION_OUTPUTS_DIR
            from hexagent.harness.definition import AgentDefinition
            from hexagent.harness.model import ModelProfile
            from hexagent.tools import PresentToUserTool
            from hexagent.tools.web import (
                BochaSearchProvider,
                BraveSearchProvider,
                FetchProvider,
                FirecrawlFetchProvider,
                JinaFetchProvider,
                SearchProvider,
                TavilySearchProvider,
            )

            from hexagent_api.config import load_config

            cfg = load_config()
            target = next((m for m in cfg.models if m.id == model_id), None)
            if not target:
                msg = f"Model config not found: {model_id}"
                raise RuntimeError(msg)

            fast_cfg = cfg.fast_model or target

            def _make_chat_model(mc: Any) -> Any:
                max_tokens = getattr(mc, "max_tokens", None) or 40960
                if mc.provider == "anthropic":
                    return ChatAnthropic(
                        model=mc.model,
                        api_key=mc.api_key,
                        base_url=mc.base_url,
                        max_tokens=max_tokens,
                    )
                if mc.provider == "yuanjing":
                    # YuanJing uses Anthropic-compatible API
                    return ChatAnthropic(
                        model=mc.model,
                        api_key=mc.api_key,
                        base_url=mc.base_url,
                        max_tokens=max_tokens,
                    )
                if mc.provider == "deepseek":
                    return ChatDeepSeek(
                        model=mc.model,
                        api_key=mc.api_key,
                        api_base=mc.base_url,
                        max_tokens=max_tokens,
                    )
                # Default: openai
                return ChatOpenAI(
                    model=mc.model,
                    api_key=mc.api_key,
                    base_url=mc.base_url,
                    max_tokens=max_tokens,
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
            elif tc.search_provider == "bocha":
                search = BochaSearchProvider(api_key=tc.search_api_key or None)

            fetch: FetchProvider | None = None
            if tc.fetch_provider == "jina":
                fetch = JinaFetchProvider(api_key=tc.fetch_api_key or None)
            elif tc.fetch_provider == "firecrawl":
                fetch = FirecrawlFetchProvider(api_key=tc.fetch_api_key or None)

            logger.info(
                "Creating agent for model=%s (%s) session=%s",
                target.display_name, target.model, session_key,
            )
            # Cowork sessions have skills mounted at /mnt/skills/{public,private}
            skill_paths = ("/mnt/skills/public", "/mnt/skills/private") if mode != "chat" else ()
            logger.info("[AgentManager] Configured skill_paths for mode=%s: %s", mode, skill_paths)

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
                skill_resolver=self._skill_resolver,
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
        """Create LocalVM and sync skills if not already running."""
        if self._vm_manager is not None:
            return

        async with self._setup_lock:
            if self._vm_manager is not None:
                return

            from hexagent.computer.local import LocalVM

            vm = LocalVM()
            await vm.start()
            self._vm_manager = vm
            
            # --- Switch from bind to cp for skills stability ---
            # Instead of mounting, we copy the skills into the VM's disk once at startup.
            # This avoids "mount loss" issues and simplifies the setup.
            await self._sync_skills_via_cp()

            # Initialize global skill resolver for the VM
            from hexagent.computer.local.vm_win import _VMSessionComputer
            from hexagent.harness import SkillResolver
            from hexagent_api.routes.skills import INACTIVE_DIR, _list_skills

            # Use a system-level computer handle for global skill discovery.
            # We point it to the root user to ensure access to /mnt/skills.
            computer = _VMSessionComputer(vm=self._vm_manager._vm, session_name="root")
            self._skill_resolver = SkillResolver(
                computer, ["/mnt/skills/public", "/mnt/skills/private"]
            )
            
            # Use the actual filesystem state (skills-inactive dir) as the source of truth
            # for disabled skills, instead of relying on config.json which might be out of sync.
            inactive_public = _list_skills(INACTIVE_DIR / "public")
            inactive_private = _list_skills(INACTIVE_DIR / "private")
            disabled_set = set(inactive_public + inactive_private)
            
            await self._skill_resolver.discover(disabled_names=disabled_set)

    async def _sync_skills_via_cp(self) -> None:
        """Synchronize skills from host to guest via 'cp' instead of bind mount.
        
        This runs once at backend startup to ensure all skills are available
        on the VM's internal disk.
        """
        assert self._vm_manager is not None
        from hexagent_api.paths import bundled_skills_dir, skills_dir
        
        # 1. Prepare host paths and ensure private dir exists
        sources = {
            "public": bundled_skills_dir() / "public",
            "private": skills_dir() / "private",
        }
        sources["private"].mkdir(parents=True, exist_ok=True)

        # 2. Cleanup any old bind mounts that might interfere
        # And ensure /mnt/skills structure exists
        cleanup_cmd = (
            "umount -l /mnt/skills/public 2>/dev/null; "
            "umount -l /mnt/skills/private 2>/dev/null; "
            "mkdir -p /mnt/skills/public /mnt/skills/private"
        )
        await self._vm_manager._vm.shell(cleanup_cmd, user="root")

        # 3. Use 'wsl --import' or direct 'cp'? 
        # Since we are in Python side, the most reliable way to 'cp' large folders
        # into WSL without permission issues is to use 'tar' through stdin.
        
        for subdir, host_path in sources.items():
            if not host_path.exists():
                continue
                
            guest_path = f"/mnt/skills/{subdir}"
            logger.info("[SkillSync] Copying %s skills from %s to %s", subdir, host_path, guest_path)
            
            # We clear the guest subdir first to handle conflicts (fresh sync)
            await self._vm_manager._vm.shell(f"rm -rf {guest_path}/*", user="root")
            
            # Use tar to stream the directory into WSL. 
            # This is much faster than individual 'wsl cp' calls and handles nested dirs.
            import subprocess
            import tarfile
            import io

            # Create tar in memory
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                # Add all contents of host_path to the root of the tar
                for item in host_path.iterdir():
                    tar.add(item, arcname=item.name)
            
            # Pipe tar to WSL
            cmd = ["wsl", "-d", self._vm_manager._vm._instance, "-u", "root", "tar", "-x", "-C", guest_path]
            process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(input=tar_stream.getvalue())
            
            if process.returncode != 0:
                logger.error("[SkillSync] Failed to sync %s skills: %s", subdir, stderr.decode())
            else:
                logger.info("[SkillSync] Successfully synced %s skills", subdir)

    async def _mount_skills(self) -> None:
        """DEPRECATED: Use _sync_skills_via_cp instead.
        
        Kept for reference but not called by current start() logic.
        """
        pass
        stale_targets: list[str] = []
        skill_mounts: list[Mount] = []
        for subdir, host_path in mount_sources.items():
            guest = f"/mnt/skills/{subdir}"
            existing = existing_by_guest.get(guest)
            if existing is not None:
                if existing.host_path == str(host_path) and host_path.is_dir():
                    continue  # already correctly mounted
                # Stale: host path changed (e.g. new _MEIPASS) or no longer exists
                logger.info(
                    "Stale skill mount detected for %s: %s (dir_exists=%s) → will replace with %s",
                    guest, existing.host_path, Path(existing.host_path).is_dir(), host_path,
                )
                stale_targets.append(f"skills/{subdir}")
            if host_path.is_dir():
                skill_mounts.append(Mount(source=str(host_path), target=f"skills/{subdir}"))

        # Deferred removal keeps lima.yaml consistent before the mount call.
        if stale_targets:
            logger.info("Removing %d stale skill mount(s): %s", len(stale_targets), stale_targets)
            await self._vm_manager.unmount(stale_targets, defer=True)

        if skill_mounts:
            logger.info("Mounting %d skill dir(s): %s", len(skill_mounts), [m.target for m in skill_mounts])
            await self._vm_manager.mount(skill_mounts)
        elif stale_targets:
            # Only removals with no replacements — apply the deferred changes now.
            await self._vm_manager.apply()

    async def start(self) -> None:
        """Initialize the agent manager.

        Loads environment variables. VM initialization is deferred until
        the first conversation that requires it (cowork mode), so the app
        can start even without Lima installed.
        """
        from dotenv import load_dotenv

        load_dotenv()
        # Keep startup fast: warm VM in background (non-blocking). Cowork
        # still lazily initializes on first use if warm-up fails.
        self._schedule_vm_warmup()
        logger.info("Agent manager initialized.")

    def _schedule_vm_warmup(self) -> None:
        """Best-effort background VM warm-up on supported hosts."""
        if self._vm_warm_task is not None and not self._vm_warm_task.done():
            return

        import shutil

        if sys.platform == "win32":
            from hexagent.computer.local._wsl import _resolve_wsl_exe

            vm_backend_available = _resolve_wsl_exe() is not None
        else:
            vm_backend_available = bool(shutil.which("limactl"))
        if not vm_backend_available:
            return

        self._vm_warm_task = asyncio.create_task(self._warm_vm_manager())

    async def _warm_vm_manager(self) -> None:
        """Background VM initialization used to auto-start installed VMs."""
        try:
            await self._ensure_vm_manager()
            logger.info("Background VM warm-up completed.")
        except Exception:
            logger.warning(
                "Background VM warm-up failed; cowork mode will initialize VM on demand.",
                exc_info=True,
            )

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
        if self._vm_warm_task is not None and not self._vm_warm_task.done():
            self._vm_warm_task.cancel()
            self._vm_warm_task = None
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

        from hexagent.computer import Mount

        new_target = Path(working_dir).name

        import shlex

        async def _is_mount_active(target_name: str) -> bool:
            guest_path = f"/sessions/{session_name}/mnt/{target_name}"
            result = await self._vm_manager._vm.shell(f"findmnt -n {shlex.quote(guest_path)}")
            return result.exit_code == 0 and bool((result.stdout or "").strip())

        # Unmount previous working dir if switching to a different one
        prev = self._session_working_dirs.get(session_name)
        prev_guest_path: str | None = None
        if prev is not None:
            prev_source, prev_target = prev
            if prev_source == working_dir:
                resolved_cwd = f"/sessions/{session_name}/mnt/{prev_target}"
                self._set_computer_default_cwd(self._computers.get(session_name), resolved_cwd)
                if await _is_mount_active(prev_target):
                    # Happy path: mount is still active and writable.
                    await self._verify_session_dir_writable(session_name, resolved_cwd)
                    return
                logger.warning(
                    "Session mount missing, forcing remount. session=%s target=%s source=%s",
                    session_name,
                    prev_target,
                    prev_source,
                )
                # Same source/target: self-heal mount in place to avoid
                # full apply/restart across all historical session mounts.
                mount = Mount(source=working_dir, target=prev_target, writable=True)
                await self._vm_manager.mount([mount], session=session_name)
                try:
                    await self._verify_session_dir_writable(session_name, resolved_cwd)
                except RuntimeError:
                    logger.warning(
                        "Writable check failed after in-place remount; forcing VM apply() and retry. session=%s",
                        session_name,
                    )
                    await self._vm_manager.apply()
                    await self._verify_session_dir_writable(session_name, resolved_cwd)
                logger.info("Remounted working dir in place %s for session %s", working_dir, session_name)
                return
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
        computer = self._computers.get(session_name)
        resolved_cwd = f"/sessions/{session_name}/mnt/{new_target}"
        self._set_computer_default_cwd(computer, resolved_cwd)
        try:
            await self._verify_session_dir_writable(session_name, resolved_cwd)
        except RuntimeError:
            # One-shot recovery: apply mounts.json to restore bind mounts if
            # WSL was restarted externally and mount state was lost.
            logger.warning("Writable check failed after mount; forcing VM apply() and retry. session=%s", session_name)
            await self._vm_manager.apply()
            await self._verify_session_dir_writable(session_name, resolved_cwd)
        logger.info("Mounted working dir %s for session %s", working_dir, session_name)

        # Remove the stale mount-point directory left behind after unmount.
        # Only do this when we switched targets; for same-target remount
        # (e.g. self-heal on lost bind mount), cleanup would remove the
        # newly restored live mount.
        if prev_guest_path is not None and prev_guest_path != resolved_cwd:
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
        # Remove any agents and their creation locks cached for this session
        keys_to_remove = [k for k in self._agents if k[1] == session_name]
        for key in keys_to_remove:
            agent = self._agents.pop(key)
            self._agent_locks.pop(key, None)
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
            await agent.aclose()
        self._agents.clear()
        self._agent_locks.clear()


# Module-level singleton
agent_manager = AgentManager()
