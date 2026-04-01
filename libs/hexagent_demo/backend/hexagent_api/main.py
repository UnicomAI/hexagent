"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from hexagent_api.agent_manager import agent_manager
from hexagent_api.paths import config_path, data_dir
from hexagent_api.routes import chat, config, conversations, sessions, setup, skills

_LOG_DIR = data_dir() / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "backend.log"

class FlushingStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        FlushingFileHandler(_LOG_FILE, encoding="utf-8"),
    ],
    force=True,
)
logger = logging.getLogger(__name__)
logger.info("Backend log file: %s", _LOG_FILE)


async def _cleanup_expired_sessions() -> None:
    """Periodically tear down unclaimed warm sessions."""
    import asyncio
    import shutil

    from hexagent_api.paths import uploads_dir
    from hexagent_api.store import session_store

    ul_dir = uploads_dir()

    while True:
        await asyncio.sleep(300)  # every 5 minutes
        try:
            for session in session_store.expired(max_age_seconds=600):
                logger.info("Cleaning up expired warm session: %s", session.id)
                await agent_manager.teardown_session(session.mode, session.session_name)
                session_store.delete(session.id)
                # Clean up any upload files left on disk
                session_uploads = ul_dir / session.id
                if session_uploads.is_dir():
                    shutil.rmtree(session_uploads)
        except Exception:
            logger.exception("Error during session cleanup")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage agent lifecycle on startup/shutdown."""
    import asyncio

    # Ensure managed VM backend binaries are on PATH before agent manager tries to find them
    from hexagent_api.routes.setup import ensure_managed_deps_on_path
    ensure_managed_deps_on_path()

    logger.info("Starting agent manager...")

    # Clear user data directory if requested by build flags (macOS only).
    # Controlled by HEXAGENT_CLEAR_USER_DATA_ON_START env var, set from
    # build_flags.json at packaging time via Electron main.js.
    if os.environ.get("HEXAGENT_CLEAR_USER_DATA_ON_START") == "1":
        import shutil as _shutil
        data = data_dir()
        if data.exists():
            logger.info("HEXAGENT_CLEAR_USER_DATA_ON_START=1 — clearing user data: %s", data)
            for item in data.iterdir():
                try:
                    if item.is_dir():
                        _shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception:
                    logger.warning("Failed to remove %s", item, exc_info=True)

        # Restore bundled config.json so pre-configured models/keys are available
        # immediately after the wipe, without waiting for Electron to re-seed it.
        bundled_config: Path | None = None
        if getattr(sys, "frozen", False):
            candidate = Path(sys._MEIPASS) / "config.json"  # type: ignore[attr-defined]
            if candidate.is_file():
                bundled_config = candidate
        if bundled_config is not None:
            dst = config_path()
            dst.parent.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(bundled_config, dst)
            logger.info("Restored bundled config.json → %s", dst)
        else:
            logger.debug("No bundled config.json found in _MEIPASS; Electron will seed it")

    await agent_manager.start()
    logger.info("Agent manager started.")

    # Tear down stale Lima instance if the app was reinstalled (macOS only).
    # Must run before the first GET /api/setup/vm so the frontend sees the
    # correct "not ready" state and shows the rebuild prompt.
    if sys.platform == "darwin":
        try:
            from hexagent_api.routes.mac_setup import teardown_lima_if_reinstalled
            await teardown_lima_if_reinstalled()
        except Exception:
            logger.exception("Failed to run Lima reinstall check at startup")
    cleanup_task = asyncio.create_task(_cleanup_expired_sessions())
    yield
    cleanup_task.cancel()
    from hexagent_api.stream_manager import stream_manager
    logger.info("Cancelling active streams...")
    stream_manager.cancel_all()
    logger.info("Shutting down agent manager...")
    await agent_manager.stop()
    logger.info("Agent manager shut down.")


app = FastAPI(title="HexAgent API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(config.router)
app.include_router(conversations.router)
app.include_router(sessions.router)
app.include_router(setup.router)
app.include_router(skills.router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
