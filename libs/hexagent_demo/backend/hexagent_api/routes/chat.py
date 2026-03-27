"""Chat endpoints — streaming agent responses via SSE."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os
import re
import shlex
import shutil
import tempfile
import time
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from starlette.background import BackgroundTask

from hexagent.computer.base import SESSION_OUTPUTS_DIR, SESSION_UPLOADS_DIR
from hexagent.exceptions import VMMountConflictError

from hexagent_api.agent_manager import agent_manager
from hexagent_api.config import load_config
from hexagent_api.models import MessageRequest
from hexagent_api.paths import pdf_cache_dir, uploads_dir
from hexagent_api.store import store
from hexagent_api.stream_manager import stream_manager

# Image extensions that should be passed as visual content to the LLM
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

logger = logging.getLogger(__name__)

router = APIRouter()


def _content_disposition(disposition: str, filename: str) -> str:
    """Build a Content-Disposition header value safe for non-ASCII filenames.

    Uses RFC 5987 ``filename*`` for Unicode names so the header stays
    latin-1 encodable (an HTTP/1.1 requirement enforced by Starlette).
    """
    try:
        filename.encode("latin-1")
        # Pure ASCII / latin-1 — simple quoting is fine
        return f'{disposition}; filename="{filename}"'
    except UnicodeEncodeError:
        # Non-ASCII: percent-encode via RFC 5987
        encoded = urllib.parse.quote(filename)
        return f"{disposition}; filename*=UTF-8''{encoded}"

UPLOADS_DIR = uploads_dir()


def _build_human_message(
    content: str,
    attachments: list[dict[str, str]] | None,
    conversation_id: str,
    *,
    model_supports_image: bool = False,
) -> HumanMessage:
    """Build a HumanMessage, embedding images as visual content blocks.

    Non-image attachments are left as text references in the content string.
    Image attachments are read from local uploads, base64-encoded, and added
    as ``image_url`` content blocks — but only if the target model supports
    image input.  Files are always uploaded to the computer regardless.

    Args:
        content: The user's text message.
        attachments: File metadata dicts with ``filename`` and ``path``.
        conversation_id: Used to locate local upload files.
        model_supports_image: Whether the target model accepts image input.
    """
    if not attachments or not model_supports_image:
        return HumanMessage(content=content)

    image_blocks: list[dict[str, object]] = []
    for att in attachments:
        ext = os.path.splitext(att["filename"])[1].lower()
        if ext not in _IMAGE_EXTENSIONS:
            continue
        # Read from local uploads directory
        local_path = UPLOADS_DIR / conversation_id / att["filename"]
        if not local_path.exists():
            logger.warning("Image attachment not found locally: %s", local_path)
            continue
        data = base64.b64encode(local_path.read_bytes()).decode("ascii")
        media_type = _IMAGE_MIME_TYPES.get(ext, "image/png")
        image_blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:{media_type};base64,{data}"},
        })

    if not image_blocks:
        return HumanMessage(content=content)

    # Build multimodal content: text block + image blocks
    blocks: list[dict[str, object]] = []
    if content:
        blocks.append({"type": "text", "text": content})
    blocks.extend(image_blocks)
    return HumanMessage(content=blocks)



@router.get("/api/chat/{conversation_id}/stream")
async def subscribe_stream(conversation_id: str) -> StreamingResponse:
    """Reconnect to an active background stream for a conversation.

    Returns the full event replay followed by live events.  If no stream
    is active, returns 204 No Content.
    """
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    active = stream_manager.get_stream(conversation_id)
    if active is None:
        return StreamingResponse(content=iter(()), status_code=204)
    return StreamingResponse(active.subscribe(), media_type="text/event-stream")


@router.post("/api/chat/{conversation_id}/message")
async def send_message(conversation_id: str, body: MessageRequest) -> StreamingResponse:
    """Send a message and stream the agent response as SSE."""
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if stream_manager.is_streaming(conversation_id):
        raise HTTPException(status_code=409, detail="Conversation already has an active stream")

    # Resolve model_id: explicit > conversation > default
    model_id = body.model_id or conv.model_id
    if not model_id:
        raise HTTPException(status_code=400, detail="No model_id specified")
    mode = conv.mode or "chat"
    session_name = conv.session_name

    # Acquire conversation lock for setup only — serialises with concurrent
    # prepare/mount operations so the session is fully ready before we stream.
    working_dir = conv.working_dir
    async with agent_manager.conversation_lock(conversation_id):
        try:
            returned_session = await agent_manager.ensure_agent(model_id, mode, session_name, working_dir=working_dir)
        except VMMountConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except Exception as exc:
            logger.exception("Failed to ensure agent")
            raise HTTPException(status_code=500, detail=str(exc)) from None
        if mode == "cowork" and returned_session and returned_session != session_name:
            conv.session_name = returned_session
            session_name = returned_session
            logger.info("Assigned session %s to conversation %s", session_name, conversation_id)

        # Ensure the conversation's working_dir is actually mounted.
        # It may differ from what the warm session had if the user switched
        # folders quickly and the PATCH didn't complete before claiming.
        if mode == "cowork" and working_dir and session_name:
            try:
                await agent_manager.mount_working_dir(session_name, working_dir)
            except VMMountConflictError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from None

    att_dicts = [a.model_dump() for a in body.attachments] if body.attachments else None
    store.add_message(conversation_id, "user", body.content, attachments=att_dicts)

    if conv.title == "New conversation":
        conv.title = body.content[:50].strip()

    # Build agent input
    cfg = load_config()
    target_model = next((m for m in cfg.models if m.id == model_id), None)
    supports_image = target_model is not None and "image" in target_model.supported_modalities

    raw_messages = store.get_messages_for_agent(conversation_id)
    messages = []
    for m in raw_messages:
        if m["role"] == "user":
            messages.append(
                _build_human_message(
                    m["content"],
                    m.get("attachments"),
                    conversation_id,
                    model_supports_image=supports_image,
                )
            )
        else:
            messages.append(AIMessage(content=m["content"]))

    input_dict = {"messages": messages}

    # Start the agent as a background task and subscribe to events
    active = stream_manager.start_stream(
        conversation_id,
        agent_manager=agent_manager,
        input_dict=input_dict,
        model_id=model_id,
        mode=mode,
        session_name=session_name,
        store=store,
        preconvert_callback=_trigger_preconvert,
    )

    return StreamingResponse(active.subscribe(), media_type="text/event-stream")


@router.post("/api/chat/{conversation_id}/upload")
async def upload_file(conversation_id: str, file: UploadFile = File(...)) -> dict[str, str]:
    """Upload a file and transfer it to the conversation's computer.

    The file is saved locally under ``uploads/{conversation_id}/`` and then
    copied into the computer via ``computer.upload()``.

    Returns the destination path inside the computer.
    """
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Read file content before acquiring lock (from HTTP request, no race)
    content = await file.read()
    mode = conv.mode or "chat"

    # Acquire conversation lock — waits for any pending prepare/mount/restart
    # to finish and prevents concurrent mount operations during upload.
    async with agent_manager.conversation_lock(conversation_id):
        session_name = conv.session_name
        computer = agent_manager.get_computer(mode, session_name)
        if computer is None:
            raise HTTPException(
                status_code=400,
                detail="Computer not ready. Send a message first to initialise the session.",
            )

        # Save to local uploads directory
        local_dir = UPLOADS_DIR / conversation_id
        local_dir.mkdir(parents=True, exist_ok=True)
        local_path = local_dir / file.filename

        if local_path.exists():
            raise HTTPException(
                status_code=409,
                detail=f'A file named "{file.filename}" already exists. Rename the file and try again.',
            )

        local_path.write_bytes(content)

        # Determine destination path inside the computer
        if mode == "chat":
            dst = f"/{SESSION_UPLOADS_DIR}/{file.filename}"
        else:
            dst = f"/sessions/{session_name}/{SESSION_UPLOADS_DIR}/{file.filename}"

        try:
            await computer.upload(str(local_path), dst)
        except FileNotFoundError as e:
            local_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(e)) from None
        except Exception as e:
            local_path.unlink(missing_ok=True)
            logger.exception("Failed to upload file to computer")
            raise HTTPException(status_code=500, detail=f"Upload to computer failed: {e}") from None

    logger.info("File uploaded: %s -> %s", file.filename, dst)
    return {"filename": file.filename, "path": dst}


@router.delete("/api/chat/{conversation_id}/upload/{filename}")
async def delete_uploaded_file(conversation_id: str, filename: str) -> dict[str, str]:
    """Delete a previously uploaded file from local storage and the computer."""
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Remove from local uploads directory
    local_path = UPLOADS_DIR / conversation_id / filename
    if local_path.exists():
        local_path.unlink()

    # Remove from computer if available
    mode = conv.mode or "chat"
    session_name = conv.session_name
    computer = agent_manager.get_computer(mode, session_name)
    if computer is not None:
        if mode == "chat":
            dst = f"/{SESSION_UPLOADS_DIR}/{filename}"
        else:
            dst = f"/sessions/{session_name}/{SESSION_UPLOADS_DIR}/{filename}"
        try:
            # For LocalVM session computers, run via the underlying VM backend (which has
            # sudo access) rather than computer.run() (which runs as the
            # unprivileged session user and can't delete root-owned uploads).
            vm = getattr(computer, "_vm", None)
            if vm is not None:
                await vm.shell(f"sudo rm -f {shlex.quote(dst)}")
            else:
                await computer.run(f"rm -f {shlex.quote(dst)}")
        except Exception:
            logger.warning("Could not remove %s from computer (may already be gone)", dst)

    logger.info("Deleted uploaded file: %s (conversation %s)", filename, conversation_id)
    return {"deleted": filename}


@router.get("/api/files/{conversation_id}")
async def download_file(
    request: Request,
    conversation_id: str,
    path: str = Query(...),
    download: bool = Query(False),
) -> StreamingResponse:
    """Download a file from the computer's output directory.

    The ``path`` query parameter must match a ``<file_path>`` value returned
    by the ``PresentToUser`` tool and must reside within the allowed output
    directory for the conversation's mode.
    """
    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    mode = conv.mode or "chat"
    session_name = conv.session_name

    # Determine the allowed output directory prefix
    if mode == "chat":
        allowed_prefix = f"/{SESSION_OUTPUTS_DIR}/"
    else:
        allowed_prefix = f"/sessions/{session_name}/{SESSION_OUTPUTS_DIR}/"

    # Security: validate the path is within the outputs directory
    if not path.startswith(allowed_prefix):
        raise HTTPException(
            status_code=403,
            detail=f"Path must be within {allowed_prefix}",
        )

    computer = agent_manager.get_computer(mode, session_name)
    if computer is None:
        raise HTTPException(
            status_code=400,
            detail="Computer not ready. Send a message first to initialise the session.",
        )

    # Download to a temp file, then stream it back
    tmp_dir = tempfile.mkdtemp()
    filename = os.path.basename(path)
    tmp_path = os.path.join(tmp_dir, filename)

    try:
        await computer.download(path, tmp_path)
    except Exception:
        # Clean up on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        os.rmdir(tmp_dir)
        raise HTTPException(
            status_code=404,
            detail=json.dumps({"error": "File not found in sandbox", "path": path}),
        ) from None

    content_type, _ = mimetypes.guess_type(filename)
    if content_type is None:
        content_type = "application/octet-stream"

    file_size = os.path.getsize(tmp_path)

    def _cleanup() -> None:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if os.path.exists(tmp_dir):
            os.rmdir(tmp_dir)

    disposition = "attachment" if download else "inline"

    # Parse Range header for partial content support (audio/video seeking)
    range_header = request.headers.get("range")
    if range_header and range_header.startswith("bytes="):
        range_spec = range_header[6:]
        start_str, _, end_str = range_spec.partition("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def _range_iterator():
            try:
                with open(tmp_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(64 * 1024, remaining))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk
            except Exception:
                logger.exception("Error reading temp file %s", tmp_path)

        return StreamingResponse(
            _range_iterator(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Disposition": _content_disposition(disposition, filename),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(length),
                "Accept-Ranges": "bytes",
            },
            background=BackgroundTask(_cleanup),
        )

    def _file_iterator():
        try:
            with open(tmp_path, "rb") as f:
                while chunk := f.read(64 * 1024):
                    yield chunk
        except Exception:
            logger.exception("Error reading temp file %s", tmp_path)

    return StreamingResponse(
        _file_iterator(),
        media_type=content_type,
        headers={
            "Content-Disposition": _content_disposition(disposition, filename),
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        },
        background=BackgroundTask(_cleanup),
    )


_FILE_PATH_RE = re.compile(r"<file_path>(.*?)</file_path>")


def _trigger_preconvert(conversation_id: str, tool_output: str) -> None:
    """Parse PresentToUser XML output and pre-convert any .pptx files."""
    for m in _FILE_PATH_RE.finditer(tool_output):
        _maybe_preconvert(conversation_id, m.group(1).strip())


_OFFICE_MIMETYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # pptx
}

_OFFICE_EXTENSIONS = {".pptx"}

# Common LibreOffice binary locations by platform
_SOFFICE_SEARCH_PATHS = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",  # macOS
    "/usr/bin/soffice",  # Linux
    "/usr/local/bin/soffice",  # Linux (manual install)
]


def _find_soffice() -> str | None:
    """Find the soffice binary on the host machine."""
    found = shutil.which("soffice")
    if found:
        return found
    for p in _SOFFICE_SEARCH_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def _cleanup_dir(dir_path: str) -> None:
    """Remove a temp directory and all its contents (best effort)."""
    shutil.rmtree(dir_path, ignore_errors=True)


# ---------------------------------------------------------------------------
# PDF cache — content-hash based, avoids re-converting identical files
# ---------------------------------------------------------------------------

_pdf_cache_dir: str | None = None


def _get_cache_dir() -> str:
    """Return (and create) a persistent cache directory for converted PDFs."""
    global _pdf_cache_dir  # noqa: PLW0603
    if _pdf_cache_dir is None:
        _pdf_cache_dir = str(pdf_cache_dir())
    os.makedirs(_pdf_cache_dir, exist_ok=True)
    return _pdf_cache_dir


def _cache_key(file_bytes: bytes) -> str:
    """Content-hash based cache key."""
    return hashlib.sha256(file_bytes).hexdigest()[:16]


def _get_cached_pdf(key: str) -> str | None:
    """Return path to cached PDF if it exists."""
    path = os.path.join(_get_cache_dir(), key + ".pdf")
    return path if os.path.isfile(path) else None


def _store_cached_pdf(key: str, pdf_path: str) -> str:
    """Copy a converted PDF into the cache. Returns the cache path."""
    cache_path = os.path.join(_get_cache_dir(), key + ".pdf")
    shutil.copy2(pdf_path, cache_path)
    return cache_path


# ---------------------------------------------------------------------------
# LibreOffice conversion
# ---------------------------------------------------------------------------


async def _convert_to_pdf(soffice_bin: str, src_path: str, out_dir: str) -> str:
    """Convert a file to PDF via soffice. Returns path to the PDF.

    Raises on failure or timeout.
    """
    proc = await asyncio.create_subprocess_exec(
        soffice_bin,
        "--headless",
        "--norestore",
        "--nofirststartwizard",
        "--convert-to", "pdf",
        "--outdir", out_dir,
        src_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise

    pdf_name = os.path.splitext(os.path.basename(src_path))[0] + ".pdf"
    pdf_path = os.path.join(out_dir, pdf_name)

    if proc.returncode != 0 or not os.path.exists(pdf_path):
        err = (stderr or b"").decode(errors="replace").strip()
        raise RuntimeError(f"soffice exit {proc.returncode}: {err or 'unknown error'}")

    return pdf_path


# ---------------------------------------------------------------------------
# Eager pre-conversion — triggered when PresentToUser emits a .pptx
# ---------------------------------------------------------------------------

# In-flight conversions keyed by (conversation_id, path) to avoid duplicates
_preconvert_tasks: dict[str, asyncio.Task[None]] = {}


async def _preconvert_office_file(
    conversation_id: str, file_path: str
) -> None:
    """Download a .pptx from the VM and convert it in the background.

    The result is stored in the PDF cache so the preview endpoint returns
    instantly when the user opens the file.
    """
    conv = store.get(conversation_id)
    if conv is None:
        return

    mode = conv.mode or "chat"
    session_name = conv.session_name
    computer = agent_manager.get_computer(mode, session_name)
    if computer is None:
        return

    soffice_bin = _find_soffice()
    if soffice_bin is None:
        return

    tmp_dir = tempfile.mkdtemp()
    filename = os.path.basename(file_path)
    src_path = os.path.join(tmp_dir, filename)

    try:
        await computer.download(file_path, src_path)

        with open(src_path, "rb") as f:
            file_bytes = f.read()
        key = _cache_key(file_bytes)

        if _get_cached_pdf(key):
            return  # already cached

        t0 = time.monotonic()
        pdf_path = await _convert_to_pdf(soffice_bin, src_path, tmp_dir)
        elapsed = time.monotonic() - t0
        _store_cached_pdf(key, pdf_path)
        logger.info("Office pre-convert: %s → cached in %.1fs", file_path, elapsed)
    except Exception:
        logger.debug("Office pre-convert failed for %s (will convert on demand)", file_path)
    finally:
        _cleanup_dir(tmp_dir)


def _maybe_preconvert(conversation_id: str, file_path: str) -> None:
    """Fire-and-forget background pre-conversion for office files."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _OFFICE_EXTENSIONS:
        return

    task_key = f"{conversation_id}:{file_path}"
    existing = _preconvert_tasks.get(task_key)
    if existing and not existing.done():
        return  # already in progress

    task = asyncio.create_task(
        _preconvert_office_file(conversation_id, file_path),
    )
    _preconvert_tasks[task_key] = task

    # Cleanup reference when done
    def _cleanup(t: asyncio.Task[None]) -> None:
        _preconvert_tasks.pop(task_key, None)

    task.add_done_callback(_cleanup)


# ---------------------------------------------------------------------------
# Preview endpoint
# ---------------------------------------------------------------------------


@router.get("/api/files/{conversation_id}/preview")
async def preview_office_file(
    conversation_id: str,
    path: str = Query(...),
) -> StreamingResponse:
    """Convert an office document to PDF via LibreOffice and stream it back.

    If the file was pre-converted (eager conversion triggered when
    PresentToUser emits a .pptx), this returns instantly from cache.
    """

    conv = store.get(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    mode = conv.mode or "chat"
    session_name = conv.session_name

    if mode == "chat":
        allowed_prefix = f"/{SESSION_OUTPUTS_DIR}/"
    else:
        allowed_prefix = f"/sessions/{session_name}/{SESSION_OUTPUTS_DIR}/"

    if not path.startswith(allowed_prefix):
        raise HTTPException(
            status_code=403,
            detail=f"Path must be within {allowed_prefix}",
        )

    ext = os.path.splitext(path)[1].lower()
    content_type, _ = mimetypes.guess_type(os.path.basename(path))
    if ext not in _OFFICE_EXTENSIONS and content_type not in _OFFICE_MIMETYPES:
        raise HTTPException(status_code=422, detail="Not an office document")

    computer = agent_manager.get_computer(mode, session_name)
    if computer is None:
        raise HTTPException(
            status_code=400,
            detail="Computer not ready. Send a message first to initialise the session.",
        )

    soffice_bin = _find_soffice()
    if soffice_bin is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "LibreOffice is not installed. "
                "Install it to enable presentation preview: "
                "brew install --cask libreoffice"
            ),
        )

    # Wait for any in-flight pre-conversion for this file
    task_key = f"{conversation_id}:{path}"
    preconvert_task = _preconvert_tasks.get(task_key)
    if preconvert_task and not preconvert_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(preconvert_task), timeout=30)
        except (asyncio.TimeoutError, Exception):
            pass  # fall through to on-demand conversion

    # Download to check cache / convert on demand
    tmp_dir = tempfile.mkdtemp()
    filename = os.path.basename(path)
    src_path = os.path.join(tmp_dir, filename)

    try:
        await computer.download(path, src_path)
    except Exception:
        logger.exception("Office preview: failed to download %s from VM", path)
        _cleanup_dir(tmp_dir)
        raise HTTPException(
            status_code=422,
            detail="Failed to download file from sandbox.",
        ) from None

    with open(src_path, "rb") as f:
        file_bytes = f.read()
    key = _cache_key(file_bytes)

    # Cache hit — return immediately
    cached = _get_cached_pdf(key)
    if cached:
        _cleanup_dir(tmp_dir)
        pdf_name = os.path.splitext(filename)[0] + ".pdf"
        return StreamingResponse(
            _read_file(cached),
            media_type="application/pdf",
            headers={"Content-Disposition": _content_disposition("inline", pdf_name)},
        )

    # On-demand conversion (pre-convert didn't finish or wasn't triggered)
    t0 = time.monotonic()
    try:
        pdf_path = await _convert_to_pdf(soffice_bin, src_path, tmp_dir)
    except asyncio.TimeoutError:
        _cleanup_dir(tmp_dir)
        raise HTTPException(status_code=422, detail="LibreOffice conversion timed out.") from None
    except Exception as exc:
        _cleanup_dir(tmp_dir)
        raise HTTPException(status_code=422, detail=str(exc)) from None

    elapsed = time.monotonic() - t0
    logger.info("Office preview: converted %s in %.1fs", path, elapsed)

    _store_cached_pdf(key, pdf_path)
    os.unlink(src_path)

    pdf_name = os.path.splitext(filename)[0] + ".pdf"
    return StreamingResponse(
        _read_file(pdf_path),
        media_type="application/pdf",
        headers={"Content-Disposition": _content_disposition("inline", pdf_name)},
        background=BackgroundTask(_cleanup_dir, tmp_dir),
    )


def _read_file(path: str):
    """Yield a file in 64KB chunks."""
    try:
        with open(path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk
    except Exception:
        logger.exception("Error reading file %s", path)
