"""In-memory conversation and session stores."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any


class WarmSession:
    """A pre-conversation warm session (VM user + home dir).

    Exists independently of any conversation.  Created when the user opens the
    welcome screen and claimed when they send their first message.
    """

    def __init__(
        self,
        session_id: str,
        mode: str,
        session_name: str | None = None,
        working_dir: str | None = None,
    ) -> None:
        self.id = session_id
        self.mode = mode
        self.session_name = session_name
        self.working_dir = working_dir
        self.created_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.id,
            "mode": self.mode,
            "session_name": self.session_name,
            "working_dir": self.working_dir,
            "created_at": self.created_at.isoformat(),
        }


class SessionStore:
    """In-memory store for warm sessions."""

    def __init__(self) -> None:
        self._sessions: dict[str, WarmSession] = {}

    def create(
        self,
        mode: str,
        session_name: str | None = None,
        working_dir: str | None = None,
    ) -> WarmSession:
        session_id = str(uuid.uuid4())
        session = WarmSession(session_id, mode, session_name=session_name, working_dir=working_dir)
        self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> WarmSession | None:
        return self._sessions.get(session_id)

    def claim(self, session_id: str) -> WarmSession | None:
        """Remove and return a session (claimed by a conversation)."""
        return self._sessions.pop(session_id, None)

    def delete(self, session_id: str) -> bool:
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def expired(self, max_age_seconds: float = 600) -> list[WarmSession]:
        """Return sessions older than max_age_seconds."""
        now = datetime.now(UTC)
        return [
            s for s in self._sessions.values()
            if (now - s.created_at).total_seconds() > max_age_seconds
        ]

    def list_all(self) -> list[WarmSession]:
        return list(self._sessions.values())


class Conversation:
    """A single conversation with its messages."""

    def __init__(
        self,
        conversation_id: str,
        title: str,
        model_id: str | None = None,
        mode: str | None = None,
        session_name: str | None = None,
        working_dir: str | None = None,
    ) -> None:
        self.id = conversation_id
        self.title = title
        self.model_id = model_id
        self.mode = mode or "chat"
        self.session_name = session_name
        self.working_dir = working_dir
        self.messages: list[dict[str, Any]] = []
        self.created_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def add_message(
        self,
        role: str,
        content: str,
        blocks: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Add a message to the conversation."""
        msg: dict[str, Any] = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if blocks:
            msg["blocks"] = blocks
        if attachments:
            msg["attachments"] = attachments
        self.messages.append(msg)
        self.updated_at = datetime.now(UTC)
        return msg

    def to_summary(self) -> dict[str, Any]:
        """Return a summary dict (no messages)."""
        return {
            "id": self.id,
            "title": self.title,
            "model_id": self.model_id,
            "mode": self.mode,
            "session_name": self.session_name,
            "working_dir": self.working_dir,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def to_detail(self) -> dict[str, Any]:
        """Return a full detail dict (with messages)."""
        return {
            "id": self.id,
            "title": self.title,
            "model_id": self.model_id,
            "mode": self.mode,
            "session_name": self.session_name,
            "working_dir": self.working_dir,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class ConversationStore:
    """In-memory dict-based storage for conversations."""

    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}

    def create(
        self,
        title: str | None = None,
        model_id: str | None = None,
        mode: str | None = None,
        working_dir: str | None = None,
    ) -> Conversation:
        """Create a new conversation."""
        conversation_id = str(uuid.uuid4())
        conv = Conversation(conversation_id, title or "New conversation", model_id=model_id, mode=mode, working_dir=working_dir)
        self._conversations[conversation_id] = conv
        return conv

    def get(self, conversation_id: str) -> Conversation | None:
        """Get a conversation by ID."""
        return self._conversations.get(conversation_id)

    def list_all(self) -> list[Conversation]:
        """List all conversations sorted by updated_at descending."""
        return sorted(
            self._conversations.values(),
            key=lambda c: c.updated_at,
            reverse=True,
        )

    def delete(self, conversation_id: str) -> bool:
        """Delete a conversation. Returns True if it existed."""
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            return True
        return False

    def update_title(self, conversation_id: str, title: str) -> Conversation | None:
        """Update a conversation's title."""
        conv = self._conversations.get(conversation_id)
        if conv is not None:
            conv.title = title
            conv.updated_at = datetime.now(UTC)
        return conv

    def update_model_id(self, conversation_id: str, model_id: str | None) -> Conversation | None:
        """Update a conversation's model_id."""
        conv = self._conversations.get(conversation_id)
        if conv is not None:
            conv.model_id = model_id
            conv.updated_at = datetime.now(UTC)
        return conv

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        blocks: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, str]] | None = None,
    ) -> dict[str, Any] | None:
        """Add a message to a conversation."""
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return None
        return conv.add_message(role, content, blocks=blocks, attachments=attachments)

    def get_messages_for_agent(self, conversation_id: str) -> list[dict[str, Any]]:
        """Get messages formatted for the agent (role + content + attachments)."""
        conv = self._conversations.get(conversation_id)
        if conv is None:
            return []
        result = []
        for m in conv.messages:
            msg: dict[str, Any] = {"role": m["role"], "content": m["content"]}
            if m.get("attachments"):
                msg["attachments"] = m["attachments"]
            result.append(msg)
        return result


# Module-level singletons
store = ConversationStore()
session_store = SessionStore()
