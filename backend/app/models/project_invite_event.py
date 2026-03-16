"""Audit event log for invite lifecycle transitions."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectInviteEvent(Base):
    """Append-only audit log for invite actions."""

    __tablename__ = "project_invite_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    invite_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_invites.id"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="info",
        index=True,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    invite: Mapped["ProjectInvite | None"] = relationship(
        "ProjectInvite",
        back_populates="events",
    )

    def __repr__(self) -> str:
        return f"<ProjectInviteEvent id={self.id} invite_id={self.invite_id} type={self.event_type}>"
