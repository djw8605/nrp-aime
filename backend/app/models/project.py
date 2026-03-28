"""Project (Allocation) model."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Integer,
    JSON,
    Numeric,
    String,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Project(Base):
    """Represents an NRP allocation / project."""

    __tablename__ = "projects"

    # -- Project lifecycle state machine -----------------------------------
    LIFECYCLE_STATE_RECEIVED = "received"
    LIFECYCLE_STATE_WAITING_PI_ACCOUNT = "waiting_pi_account"
    LIFECYCLE_STATE_PENDING_PROVISIONING = "pending_provisioning"
    LIFECYCLE_STATE_PROVISIONING = "provisioning"
    LIFECYCLE_STATE_PROVISIONING_FAILED = "provisioning_failed"
    LIFECYCLE_STATE_PROVISIONED = "provisioned"
    LIFECYCLE_STATE_AIME_NOTIFIED = "aime_notified"
    LIFECYCLE_STATE_ACTIVE = "active"
    LIFECYCLE_STATE_INACTIVE = "inactive"

    LIFECYCLE_STATES = (
        LIFECYCLE_STATE_RECEIVED,
        LIFECYCLE_STATE_WAITING_PI_ACCOUNT,
        LIFECYCLE_STATE_PENDING_PROVISIONING,
        LIFECYCLE_STATE_PROVISIONING,
        LIFECYCLE_STATE_PROVISIONING_FAILED,
        LIFECYCLE_STATE_PROVISIONED,
        LIFECYCLE_STATE_AIME_NOTIFIED,
        LIFECYCLE_STATE_ACTIVE,
        LIFECYCLE_STATE_INACTIVE,
    )

    LIFECYCLE_STATE_TRANSITIONS: dict[str, set[str]] = {
        LIFECYCLE_STATE_RECEIVED: {
            LIFECYCLE_STATE_PENDING_PROVISIONING,
        },
        LIFECYCLE_STATE_PENDING_PROVISIONING: {
            LIFECYCLE_STATE_PROVISIONING,
        },
        LIFECYCLE_STATE_PROVISIONING: {
            LIFECYCLE_STATE_PROVISIONED,
            LIFECYCLE_STATE_PROVISIONING_FAILED,
        },
        LIFECYCLE_STATE_PROVISIONING_FAILED: {
            LIFECYCLE_STATE_PROVISIONING,  # retry
        },
        LIFECYCLE_STATE_PROVISIONED: {
            LIFECYCLE_STATE_WAITING_PI_ACCOUNT,
            LIFECYCLE_STATE_AIME_NOTIFIED,
        },
        LIFECYCLE_STATE_WAITING_PI_ACCOUNT: {
            LIFECYCLE_STATE_PROVISIONED,  # PI completed → ready for notification
        },
        LIFECYCLE_STATE_AIME_NOTIFIED: {
            LIFECYCLE_STATE_ACTIVE,
        },
        LIFECYCLE_STATE_ACTIVE: {
            LIFECYCLE_STATE_INACTIVE,
        },
        LIFECYCLE_STATE_INACTIVE: {
            LIFECYCLE_STATE_ACTIVE,  # reactivation
        },
    }

    # Legacy aliases mapping old provisioning_state values.
    PROVISIONING_STATE_RECEIVED = "received"
    PROVISIONING_STATE_PROVISIONING = "provisioning"
    PROVISIONING_STATE_READY = "ready"
    PROVISIONING_STATE_FAILED = "failed"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aime_allocation_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    grant_number: Mapped[str | None] = mapped_column(String, index=True)
    allocation_record_id: Mapped[str | None] = mapped_column(String, index=True)
    site_project_id: Mapped[str | None] = mapped_column(String, index=True)
    allocation_type: Mapped[str | None] = mapped_column(String, nullable=True)
    request_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_packet_rec_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    source_trans_rec_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    source_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    source_site_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allocated_resource: Mapped[str | None] = mapped_column(String, nullable=True)
    service_units_allocated: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    service_units_remaining: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_title: Mapped[str | None] = mapped_column(String, nullable=True)
    pfos_number: Mapped[str | None] = mapped_column(String, nullable=True)
    board_type: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_person_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_email: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_organization: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_org_code: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_department: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_business_phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String, nullable=True)
    cpu_allocated: Mapped[int] = mapped_column(Integer, default=0)
    gpu_allocated: Mapped[int] = mapped_column(Integer, default=0)
    kubernetes_namespace: Mapped[str | None] = mapped_column(String, nullable=True)
    authentik_group_name: Mapped[str | None] = mapped_column(String, nullable=True)
    lifecycle_state: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=LIFECYCLE_STATE_RECEIVED,
        index=True,
    )
    provisioning_state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PROVISIONING_STATE_RECEIVED,
    )
    provisioning_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provisioning_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provisioning_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provisioning_last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    provisioning_alerted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project_users: Mapped[list["ProjectUser"]] = relationship(
        "ProjectUser", back_populates="project", cascade="all, delete-orphan"
    )
    invites: Mapped[list["ProjectInvite"]] = relationship(
        "ProjectInvite",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    usage_snapshot: Mapped["ProjectUsageSnapshot | None"] = relationship(
        "ProjectUsageSnapshot",
        back_populates="project",
        uselist=False,
        cascade="all, delete-orphan",
    )
    usage_exports: Mapped[list["AMIEUsageExport"]] = relationship(
        "AMIEUsageExport",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r}>"

    def set_lifecycle_state(self, state: str) -> None:
        """Transition to a new lifecycle state with validation."""
        if state not in self.LIFECYCLE_STATES:
            raise ValueError(f"Unknown lifecycle state: {state}")
        self.lifecycle_state = state

    def can_lifecycle_transition_to(self, target: str) -> bool:
        """Return whether *target* is a valid next lifecycle state."""
        allowed = self.LIFECYCLE_STATE_TRANSITIONS.get(self.lifecycle_state)
        if allowed is None:
            return False
        return target in allowed


@event.listens_for(Project, "before_delete")
def _prevent_project_hard_delete(mapper, connection, target):  # noqa: ARG001
    """Guard against accidental hard deletion of Project rows.

    Hard deletion is intentionally disallowed; use ``is_active = False`` for
    soft-deactivation instead.  This listener raises an error if any code path
    attempts to issue a ``DELETE`` on a Project row so that the cascade
    relationships (project_users, invites, usage_snapshot, usage_exports) are
    never silently wiped.
    """
    raise ValueError(
        f"Hard deletion of Project {target.id!r} ({target.name!r}) is not allowed. "
        "Set is_active=False to deactivate a project instead."
    )
