"""Pydantic request/response models for the OpenAgent API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentInfo(BaseModel):
    """Metadata for an uploaded file attached to a message."""

    filename: str = Field(..., description="Original filename")
    path: str = Field(..., description="Path inside the computer/VM")


class MessageRequest(BaseModel):
    """Request body for sending a chat message."""

    content: str = Field(..., min_length=1, description="The user message content")
    model_id: str | None = Field(None, description="Optional model config ID to use")
    attachments: list[AttachmentInfo] | None = Field(None, description="Attached files")


class ConversationCreateRequest(BaseModel):
    """Request body for creating a conversation."""

    title: str | None = Field(None, description="Optional title for the conversation")
    model_id: str | None = Field(None, description="Optional model config ID to use")
    mode: str | None = Field(None, description="Conversation mode: 'chat' or 'cowork'")
    working_dir: str | None = Field(None, description="Host folder path to mount (cowork mode)")
    session_id: str | None = Field(None, description="Warm session ID to claim")


class ConversationUpdateRequest(BaseModel):
    """Request body for updating a conversation."""

    title: str | None = Field(None, min_length=1, description="New title for the conversation")
    model_id: str | None = Field(None, description="Optional model config ID to use")
    working_dir: str | None = Field(None, description="Host folder path to mount (cowork mode)")


class MessageResponse(BaseModel):
    """A single message in a conversation."""

    role: str
    content: str
    timestamp: datetime


class ConversationSummary(BaseModel):
    """Summary of a conversation (without messages)."""

    id: str
    title: str
    model_id: str | None = None
    mode: str | None = None
    session_name: str | None = None
    working_dir: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDetail(BaseModel):
    """Full conversation with messages."""

    id: str
    title: str
    model_id: str | None = None
    mode: str | None = None
    session_name: str | None = None
    working_dir: str | None = None
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime
