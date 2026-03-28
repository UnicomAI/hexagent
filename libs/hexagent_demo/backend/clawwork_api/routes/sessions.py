"""Warm session endpoints — pre-conversation VM session management."""

from __future__ import annotations

import logging
import shlex
import shutil

from fastapi import APIRouter, HTTPException, UploadFile, File
from pathlib import Path
from pydantic import BaseModel, Field

from clawwork.computer.base import SESSION_UPLOADS_DIR
from clawwork.exceptions import VMMountConflictError

from clawwork_api.agent_manager import agent_manager
from clawwork_api.paths import uploads_dir
from clawwork_api.store import session_store

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOADS_DIR = uploads_dir()


class SessionCreateRequest(BaseModel):
    mode: str = Field("cowork", description="Session mode: 'chat' or 'cowork'")
    model_id: str | None = Field(None, description="Model config ID for eager agent creation")
    working_dir: str | None = Field(None, description="Host folder to mount (cowork)")


class SessionUpdateRequest(BaseModel):
    working_dir: str | None = Field(None, description="Host folder to mount (cowork)")


@router.post("/api/sessions", status_code=201)
async def create_session(body: SessionCreateRequest | None = None) -> dict:
    """Create a warm session (VM user + home dir).

    Called when the user opens the welcome screen to pre-warm infrastructure
    before a conversation exists.

    Returns as soon as the VM session is ready (so uploads work immediately).
    Agent creation (skill resolution, MCP connects) runs in the background
    to avoid blocking the response.
    """
    mode = body.mode if body else "cowork"
    model_id = body.model_id if body else None
    working_dir = body.working_dir if body else None

    # Create the VM session
    session = session_store.create(mode=mode)

    async with agent_manager.conversation_lock(session.id):
        try:
            session_name = await agent_manager.ensure_session(
                mode, session_name=None, working_dir=working_dir,
            )
        except VMMountConflictError as exc:
            await agent_manager.teardown_session(mode, session.session_name)
            session_store.delete(session.id)
            raise HTTPException(status_code=409, detail=str(exc)) from None

        session.session_name = session_name
        session.working_dir = working_dir

        # Mount working dir if provided on an existing session
        if mode == "cowork" and working_dir and session_name:
            try:
                await agent_manager.mount_working_dir(session_name, working_dir)
            except VMMountConflictError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from None

    logger.info("Warm session created: %s (session_name=%s)", session.id, session.session_name)

    # Eagerly create the agent in background (skill resolution, MCP connects,
    # etc.) so it's cached when the user sends their first message.  This runs
    # outside the lock so the HTTP response returns immediately.
    if model_id:
        import asyncio

        async def _warm_agent() -> None:
            try:
                await agent_manager.ensure_agent(
                    model_id, mode, session.session_name, working_dir=working_dir,
                )
            except Exception:
                logger.warning(
                    "Eager agent creation failed for session %s (will retry on first message)",
                    session.id,
                )

        asyncio.create_task(_warm_agent())

    return session.to_dict()


@router.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, body: SessionUpdateRequest) -> dict:
    """Update a warm session (e.g. change working directory mount)."""
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    async with agent_manager.conversation_lock(session_id):
        # Re-check after lock — session may have been claimed by conversation creation
        if session_store.get(session_id) is None:
            raise HTTPException(status_code=404, detail="Session was claimed by a conversation")

        if body.working_dir is not None and session.mode == "cowork" and session.session_name:
            try:
                await agent_manager.mount_working_dir(session.session_name, body.working_dir)
            except VMMountConflictError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from None
            session.working_dir = body.working_dir

    return session.to_dict()


@router.post("/api/sessions/{session_id}/upload")
async def upload_session_file(
    session_id: str, file: UploadFile = File(...),
) -> dict[str, str]:
    """Upload a file to a warm session's computer.

    Files are stored under ``uploads/{session_id}/`` locally and copied into the
    session's uploads directory inside the computer.
    """
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    content = await file.read()
    mode = session.mode

    async with agent_manager.conversation_lock(session_id):
        computer = agent_manager.get_computer(mode, session.session_name)
        if computer is None:
            raise HTTPException(
                status_code=400,
                detail="Computer not ready. Session may still be initializing.",
            )

        local_dir = UPLOADS_DIR / session_id
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / file.filename

        if local_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f'A file named "{file.filename}" already exists. Rename the file and try again.',
            )

        local_path.write_bytes(content)

        if mode == "chat":
            dst = f"/{SESSION_UPLOADS_DIR}/{file.filename}"
        else:
            dst = f"/sessions/{session.session_name}/{SESSION_UPLOADS_DIR}/{file.filename}"

        try:
            await computer.upload(str(local_path), dst)
        except FileNotFoundError as e:
            local_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(e)) from None
        except Exception as e:
            local_path.unlink(missing_ok=True)
            logger.exception("Failed to upload file to computer")
            raise HTTPException(status_code=500, detail=f"Upload to computer failed: {e}") from None

    logger.info("File uploaded to session %s: %s -> %s", session_id, file.filename, dst)
    return {"filename": file.filename, "path": dst}


@router.delete("/api/sessions/{session_id}/upload/{filename}")
async def delete_session_file(session_id: str, filename: str) -> dict[str, str]:
    """Delete a file from a warm session."""
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    local_path = UPLOADS_DIR / session_id / filename
    if local_path.exists():
        local_path.unlink()

    mode = session.mode
    computer = agent_manager.get_computer(mode, session.session_name)
    if computer is not None:
        if mode == "chat":
            dst = f"/{SESSION_UPLOADS_DIR}/{filename}"
        else:
            dst = f"/sessions/{session.session_name}/{SESSION_UPLOADS_DIR}/{filename}"
        try:
            vm = getattr(computer, "_vm", None)
            if vm is not None:
                await vm.shell(f"sudo rm -f {shlex.quote(dst)}")
            else:
                await computer.run(f"rm -f {shlex.quote(dst)}")
        except Exception:
            logger.warning("Could not remove %s from computer (may already be gone)", dst)

    logger.info("Deleted file from session %s: %s", session_id, filename)
    return {"deleted": filename}


@router.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    """Explicitly tear down a warm session and its resources."""
    session = session_store.claim(session_id)
    if session is None:
        return  # already claimed or expired — no-op

    await agent_manager.teardown_session(session.mode, session.session_name)

    uploads = UPLOADS_DIR / session_id
    if uploads.is_dir():
        shutil.rmtree(uploads)

    logger.info("Deleted warm session: %s", session_id)
