"""Background stream manager for decoupling agent execution from HTTP lifecycle.

Agent responses run as background ``asyncio.Task`` instances that write SSE
events into a per-conversation buffer.  SSE endpoints become thin consumers
that can connect, disconnect, and reconnect freely — the buffer is the source
of truth.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Callable, Literal

logger = logging.getLogger(__name__)

_CLEANUP_DELAY_SECONDS = 120.0


class ConversationStream:
    """Per-conversation event buffer with fan-out to live subscribers."""

    __slots__ = (
        "conversation_id",
        "msg_id",
        "status",
        "events",
        "_subscribers",
        "_task",
        "_created_at",
    )

    def __init__(
        self,
        conversation_id: str,
        msg_id: str,
        task: asyncio.Task,  # type: ignore[type-arg]
    ) -> None:
        self.conversation_id = conversation_id
        self.msg_id = msg_id
        self.status: Literal["streaming", "done", "error"] = "streaming"
        self.events: list[str] = []
        self._subscribers: set[asyncio.Queue[str | None]] = set()
        self._task = task
        self._created_at = time.monotonic()

    def push(self, event_str: str) -> None:
        """Append an SSE event string to the buffer and notify subscribers."""
        self.events.append(event_str)
        for q in self._subscribers:
            q.put_nowait(event_str)

    def finish(self, status: Literal["done", "error"]) -> None:
        """Mark the stream as complete and wake all subscribers."""
        self.status = status
        for q in self._subscribers:
            q.put_nowait(None)  # sentinel

    async def subscribe(self, last_event_idx: int = 0) -> AsyncIterator[str]:
        """Yield SSE events, replaying from *last_event_idx* then live.

        The caller can break out or let the iterator end naturally when the
        stream finishes (``None`` sentinel).

        Ordering guarantee: the queue is registered in ``_subscribers``
        *before* taking the replay snapshot, and both happen synchronously
        (no ``await`` in between).  Since ``push()`` appends to ``events``
        and enqueues in a single synchronous call, there is no window for
        an event to be missed or duplicated.
        """
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            # Replay buffered events the subscriber missed.
            # Snapshot length taken synchronously after queue registration.
            snapshot_len = len(self.events)
            for event_str in self.events[last_event_idx:snapshot_len]:
                yield event_str

            # If the stream already finished, nothing more to wait for.
            if self.status != "streaming":
                return

            # Live events from the queue.
            while True:
                item = await queue.get()
                if item is None:
                    return
                yield item
        finally:
            self._subscribers.discard(queue)


class StreamManager:
    """Manages background agent tasks and their event buffers."""

    def __init__(self) -> None:
        self._streams: dict[str, ConversationStream] = {}
        self._cleanup_handles: dict[str, asyncio.TimerHandle] = {}

    def get_stream(self, conversation_id: str) -> ConversationStream | None:
        return self._streams.get(conversation_id)

    def start_stream(
        self,
        conversation_id: str,
        generator_factory: Callable[[], AsyncIterator[str]],
        msg_id: str,
    ) -> ConversationStream:
        """Spawn a background task that consumes *generator_factory* and buffers events."""
        # Cancel any pending cleanup for this conversation (e.g. user sent a
        # new message right after previous stream finished).
        handle = self._cleanup_handles.pop(conversation_id, None)
        if handle is not None:
            handle.cancel()

        # We need the stream reference inside _run, so create it with a
        # temporary task, then immediately replace with the real one.
        # Both happen synchronously before yielding to the event loop,
        # so _run never sees the dummy.
        dummy_task: asyncio.Task[None] = asyncio.get_running_loop().create_future()  # type: ignore[assignment]
        stream = ConversationStream(conversation_id, msg_id, dummy_task)
        task = asyncio.create_task(
            self._run(stream, generator_factory),
            name=f"stream-{conversation_id}",
        )
        stream._task = task
        self._streams[conversation_id] = stream
        return stream

    async def _run(
        self,
        stream: ConversationStream,
        generator_factory: Callable[[], AsyncIterator[str]],
    ) -> None:
        """Consume the async generator and push events into the stream."""
        status: Literal["done", "error"] = "done"
        try:
            async for event_str in generator_factory():
                stream.push(event_str)
        except asyncio.CancelledError:
            logger.info("Stream cancelled for %s", stream.conversation_id)
            # Send an interrupt event to the frontend before closing
            stream.push("event: message_interrupt\ndata: {}\n\n")
            status = "done"  # It's an intentional interrupt, not a fatal error
        except Exception:
            logger.exception(
                "Background stream error for %s", stream.conversation_id
            )
            status = "error"
        finally:
            stream.finish(status)
            self._schedule_cleanup(stream.conversation_id)

    def _schedule_cleanup(self, conversation_id: str) -> None:
        """Remove stream buffer after a TTL so reconnecting clients can replay."""
        loop = asyncio.get_running_loop()
        handle = loop.call_later(
            _CLEANUP_DELAY_SECONDS,
            self._do_cleanup,
            conversation_id,
        )
        self._cleanup_handles[conversation_id] = handle

    def _do_cleanup(self, conversation_id: str) -> None:
        self._streams.pop(conversation_id, None)
        self._cleanup_handles.pop(conversation_id, None)
        logger.debug("Cleaned up stream buffer for %s", conversation_id)

    def cancel_all(self) -> None:
        """Cancel all active stream tasks (used during shutdown)."""
        for stream in self._streams.values():
            if not stream._task.done():
                stream._task.cancel()
        for handle in self._cleanup_handles.values():
            handle.cancel()
        self._cleanup_handles.clear()


stream_manager = StreamManager()
