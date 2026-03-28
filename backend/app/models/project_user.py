"""ProjectUser association model."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
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

    # -- Account lifecycle state machine -----------------------------------
    # States (ordered by progression):
    ACCOUNT_STATE_RECEIVED = "received"
    ACCOUNT_STATE_EMAIL_INVITE_SENT = "email_invite_sent"
    ACCOUNT_STATE_USER_COMPLETED_OAUTH = "user_completed_oauth"
    ACCOUNT_STATE_AIME_NOTIFIED = "aime_notified"
    # PI-specific terminal state: account covered by notify_project_create
    ACCOUNT_STATE_COVERED_BY_PROJECT = "covered_by_project_notification"

    ACCOUNT_STATES = (
        ACCOUNT_STATE_RECEIVED,
        ACCOUNT_STATE_EMAIL_INVITE_SENT,
        ACCOUNT_STATE_USER_COMPLETED_OAUTH,
        ACCOUNT_STATE_AIME_NOTIFIED,
        ACCOUNT_STATE_COVERED_BY_PROJECT,
    )

    # Valid transitions: from_state -> set of allowed next states.
    ACCOUNT_STATE_TRANSITIONS: dict[str, set[str]] = {
        ACCOUNT_STATE_RECEIVED: {
            ACCOUNT_STATE_EMAIL_INVITE_SENT,
        },
        ACCOUNT_STATE_EMAIL_INVITE_SENT: {
            ACCOUNT_STATE_USER_COMPLETED_OAUTH,
        },
        ACCOUNT_STATE_USER_COMPLETED_OAUTH: {
            ACCOUNT_STATE_AIME_NOTIFIED,
            ACCOUNT_STATE_COVERED_BY_PROJECT,
        },
        ACCOUNT_STATE_AIME_NOTIFIED: set(),  # terminal
        ACCOUNT_STATE_COVERED_BY_PROJECT: set(),  # terminal
    }

    # Rank for monotonic forward-only progression when updating existing rows.
    ACCOUNT_STATE_RANK: dict[str, int] = {
        ACCOUNT_STATE_RECEIVED: 1,
        ACCOUNT_STATE_EMAIL_INVITE_SENT: 2,
        ACCOUNT_STATE_USER_COMPLETED_OAUTH: 3,
        ACCOUNT_STATE_AIME_NOTIFIED: 4,
        ACCOUNT_STATE_COVERED_BY_PROJECT: 4,
    }

    # Legacy aliases for backwards compatibility with old DB values.
    ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE = "not_sent_email_invite"
    ACCOUNT_STATE_JUST_RECEIVED_PACKET = ACCOUNT_STATE_RECEIVED
    ACCOUNT_STATE_JUST_RECEIVED_PACKET_LEGACY = "just_received_packet"
    ACCOUNT_STATE_SENT_EMAIL = "sent_email"
    ACCOUNT_STATE_ACCOUNT_MADE = "account_made"

    # All values that are valid in the database (current + legacy).
    ALL_ACCOUNT_STATES = ACCOUNT_STATES + (
        ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE,
        ACCOUNT_STATE_JUST_RECEIVED_PACKET_LEGACY,
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
    allocated_resource: Mapped[str | None] = mapped_column(String, nullable=True)
    service_units_allocated: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    service_units_remaining: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    remote_site_login: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    account_state: Mapped[str] = mapped_column(
        String, nullable=False, default=ACCOUNT_STATE_RECEIVED, index=True
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
        """Update state and timestamp together.

        Validates that ``state`` is a known account state.  When the current
        state is one of the canonical state-machine values, the transition is
        also checked against :attr:`ACCOUNT_STATE_TRANSITIONS` so that only
        forward progress is allowed.
        """
        if state not in self.ALL_ACCOUNT_STATES:
            raise ValueError(f"Unknown account state: {state}")
        self.account_state = state
        self.account_state_updated_at = datetime.now(UTC)

    def can_transition_to(self, target: str) -> bool:
        """Return whether *target* is a valid next state from the current one."""
        allowed = self.ACCOUNT_STATE_TRANSITIONS.get(self.account_state)
        if allowed is None:
            return False
        return target in allowed
