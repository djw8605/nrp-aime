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

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aime_allocation_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    grant_number: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    allocation_record_id: Mapped[str | None] = mapped_column(
        String, unique=True, index=True
    )
    site_project_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)
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
    service_units_allocated: Mapped[Decimal | None] = mapped_column(
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
        "ProjectUsageSnapshot", back_populates="project", uselist=False
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name!r}>"


@event.listens_for(Project, "before_delete")
def _prevent_project_delete(_mapper, _connection, target: Project) -> None:
    """Disallow hard deletion; projects are inactivated instead."""
    raise ValueError(
        f"Project deletion is not allowed (project_id={target.id}). "
        "Set is_active=False instead."
    )
