"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openagent_api.agent_manager import agent_manager
from openagent_api.routes import chat, config, conversations, sessions, setup, skills

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _cleanup_expired_sessions() -> None:
    """Periodically tear down unclaimed warm sessions."""
    import asyncio
    import shutil

    from openagent_api.paths import uploads_dir
    from openagent_api.store import session_store

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
    from openagent_api.routes.setup import ensure_managed_deps_on_path
    ensure_managed_deps_on_path()

    logger.info("Starting agent manager...")
    await agent_manager.start()
    logger.info("Agent manager started.")
    cleanup_task = asyncio.create_task(_cleanup_expired_sessions())
    yield
    cleanup_task.cancel()
    logger.info("Shutting down agent manager...")
    await agent_manager.stop()
    logger.info("Agent manager shut down.")


app = FastAPI(title="OpenAgent API", version="0.1.0", lifespan=lifespan)

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
