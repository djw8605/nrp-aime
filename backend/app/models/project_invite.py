"""Project invite model for special-link onboarding flow."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectInvite(Base):
    """One-time invite token metadata for project onboarding."""

    __tablename__ = "project_invites"

    STATUS_PENDING = "pending"
    STATUS_USED = "used"
    STATUS_EXPIRED = "expired"
    STATUS_REVOKED = "revoked"
    STATUSES = (
        STATUS_PENDING,
        STATUS_USED,
        STATUS_EXPIRED,
        STATUS_REVOKED,
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String, nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=STATUS_PENDING, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    invited_by: Mapped[str | None] = mapped_column(String, nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    authentik_group_name: Mapped[str | None] = mapped_column(String, nullable=True)
    redirect_path: Mapped[str | None] = mapped_column(String, nullable=True)
    invite_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project | None"] = relationship("Project", back_populates="invites")
    user: Mapped["User | None"] = relationship("User", back_populates="invites")
    events: Mapped[list["ProjectInviteEvent"]] = relationship(
        "ProjectInviteEvent",
        back_populates="invite",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectInvite id={self.id} project_id={self.project_id} "
            f"user_id={self.user_id} status={self.status}>"
        )
