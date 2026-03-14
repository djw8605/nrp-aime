"""ProjectUser association model."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ProjectUser(Base):
    """Association between a Project and a User, with an optional role."""

    __tablename__ = "project_users"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "user_id", "resource", name="uq_project_user_resource"
        ),
    )
    ACCOUNT_STATE_JUST_RECEIVED_PACKET = "just_received_packet"
    ACCOUNT_STATE_SENT_EMAIL = "sent_email"
    ACCOUNT_STATE_ACCOUNT_MADE = "account_made"
    ACCOUNT_STATES = (
        ACCOUNT_STATE_JUST_RECEIVED_PACKET,
        ACCOUNT_STATE_SENT_EMAIL,
        ACCOUNT_STATE_ACCOUNT_MADE,
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    resource: Mapped[str | None] = mapped_column(String, nullable=True)
    remote_site_login: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    account_state: Mapped[str] = mapped_column(
        String, nullable=False, default=ACCOUNT_STATE_JUST_RECEIVED_PACKET, index=True
    )
    account_state_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_made_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aime_confirmation_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    source_packet_rec_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    source_trans_rec_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    source_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="project_users")
    user: Mapped["User"] = relationship("User", back_populates="project_users")

    def __repr__(self) -> str:
        return f"<ProjectUser project={self.project_id} user={self.user_id}>"

    def set_account_state(self, state: str) -> None:
        """Update state and timestamp together."""
        if state not in self.ACCOUNT_STATES:
            raise ValueError(f"Unknown account state: {state}")
        self.account_state = state
        self.account_state_updated_at = datetime.now(UTC)
