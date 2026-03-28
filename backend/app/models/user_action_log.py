"""User action/audit log model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserActionLog(Base):
    """Append-only log of user-facing actions (emails, OAuth flows, etc.)."""

    __tablename__ = "user_action_logs"

    EVENT_EMAIL_SENT = "email_sent"
    EVENT_OAUTH_FLOW_STARTED = "oauth_flow_started"
    EVENT_OAUTH_FLOW_COMPLETED = "oauth_flow_completed"
    EVENT_OAUTH_FLOW_FAILED = "oauth_flow_failed"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
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

    user: Mapped["User | None"] = relationship(
        "User",
        back_populates="action_logs",
    )

    def __repr__(self) -> str:
        return f"<UserActionLog id={self.id} user_id={self.user_id} type={self.event_type}>"
