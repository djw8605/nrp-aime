"""Schemas for project invite onboarding endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class InviteCreateRequest(BaseModel):
    """Payload for creating a new project invite."""

    email: EmailStr
    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    invited_by: str | None = None
    authentik_group_name: str | None = None
    redirect_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    send_email: bool = True


class InviteCreateResponse(BaseModel):
    """Response for invite creation."""

    id: uuid.UUID
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    email: EmailStr
    status: str
    expires_at: datetime
    invite_url: str
    email_dispatched: bool


class InvitePreviewResponse(BaseModel):
    """Safe preview payload for frontend invite-accept view."""

    valid: bool
    status: str | None = None
    user_id: uuid.UUID | None = None
    user_name: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    project_names: list[str] = Field(default_factory=list)
    project_count: int = 0
    invited_email_masked: str | None = None
    expires_at: datetime | None = None
    message: str


class InviteFinalizeResult(BaseModel):
    """Result metadata after successful callback finalization."""

    invite_id: uuid.UUID
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID
    project_user_id: uuid.UUID | None = None
    status: str
    username: str | None = None


class InviteErrorResponse(BaseModel):
    """Safe invite error payload for API responses."""

    error_code: str
    message: str
