"""Conversation CRUD endpoints."""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

from clawwork_api.agent_manager import agent_manager
from clawwork_api.models import ConversationCreateRequest, ConversationUpdateRequest
from clawwork_api.paths import uploads_dir
from clawwork_api.store import session_store, store
from clawwork_api.stream_manager import stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOADS_DIR = uploads_dir()


@router.post("/api/browse-folder")
async def browse_folder() -> dict:
    """Open a native OS folder picker and return the selected path."""
    if sys.platform == "darwin":
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e",
            'return POSIX path of (choose folder with prompt "Select a folder")',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"path": None}
        if proc.returncode != 0:
            return {"path": None}
        path = stdout.decode().strip().rstrip("/")
        return {"path": path}

    if sys.platform == "win32":
        # PowerShell-based folder picker — works on all Windows 10+ builds.
        ps_script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "if ($f.ShowDialog() -eq 'OK') { $f.SelectedPath } else { '' }"
        )
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-NoProfile", "-Command", ps_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {"path": None}
        if proc.returncode != 0:
            return {"path": None}
        path = stdout.decode().strip()
        return {"path": path or None}

    raise HTTPException(status_code=501, detail=f"Folder picker not supported on {sys.platform}")


def _enrich_with_stream_status(d: dict, conversation_id: str) -> dict:
    """Add streaming metadata to a conversation dict."""
    stream = stream_manager.get_stream(conversation_id)
    if stream is not None and stream.status == "streaming":
        d["streaming"] = True
        d["stream_msg_id"] = stream.msg_id
        d["stream_event_count"] = len(stream.events)
    else:
        d["streaming"] = False
    return d


@router.get("/api/conversations")
async def list_conversations() -> list[dict]:
    """List all conversations sorted by updated_at descending."""
    return [_enrich_with_stream_status(c.to_detail(), c.id) for c in store.list_all()]


@router.post("/api/conversations", status_code=201)
async def create_conversation(body: ConversationCreateRequest | None = None) -> dict:
    """Create a new conversation, optionally claiming a warm session."""
    title = body.title if body else None
    model_id = body.model_id if body else None
    mode = body.mode if body else None
    working_dir = body.working_dir if body else None
    session_id = body.session_id if body else None

    conv = store.create(title=title, model_id=model_id, mode=mode, working_dir=working_dir)

    # Claim the warm session if provided.
    # claim() is a dict.pop() — instant, no lock needed.  Any in-flight PATCH
    # (folder mount) will see the session gone on its re-check and 404 harmlessly.
    # The chat route ensures the correct working_dir is mounted before streaming.
    if session_id:
        warm = session_store.claim(session_id)
        if warm is not None:
            conv.session_name = warm.session_name
            # Use warm session's working_dir if conversation didn't specify one
            if not working_dir and warm.working_dir:
                conv.working_dir = warm.working_dir

            # Move local upload files from session dir to conversation dir
            session_uploads = UPLOADS_DIR / session_id
            if session_uploads.is_dir():
                conv_uploads = UPLOADS_DIR / conv.id
                conv_uploads.mkdir(parents=True, exist_ok=True)
                for f in session_uploads.iterdir():
                    shutil.move(str(f), str(conv_uploads / f.name))
                session_uploads.rmdir()

            logger.info(
                "Conversation %s claimed warm session %s (session_name=%s)",
                conv.id, session_id, warm.session_name,
            )

    return conv.to_detail()


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: str) -> dict:
    """Get a conversation with messages."""
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _enrich_with_stream_status(conv.to_detail(), conversation_id)


@router.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation. Tears down the session if it has no messages."""
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    mode = conv.mode or "chat"
    # Tear down session if conversation was never used
    if not conv.messages:
        await agent_manager.teardown_session(mode, conv.session_name)

    store.delete(conversation_id)


@router.patch("/api/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, body: ConversationUpdateRequest) -> dict:
    """Update a conversation's title and/or model_id."""
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if body.title is not None:
        store.update_title(conversation_id, body.title)
    if body.model_id is not None:
        store.update_model_id(conversation_id, body.model_id)
    if body.working_dir is not None:
        conv.working_dir = body.working_dir
    return conv.to_summary()
