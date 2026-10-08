"""Ledger of daily GPU usage reported to the ACCESS Usage API."""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GpuUsageRecord(Base):
    """GPU hours for one AMIE username in one project on one UTC day."""

    __tablename__ = "gpu_usage_records"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "usage_date",
            "username",
            name="uq_gpu_usage_project_date_username",
        ),
    )

    STATUS_PENDING = "pending"
    STATUS_SUBMITTED = "submitted"
    STATUS_LOADED = "loaded"
    STATUS_FAILED = "failed"
    STATUSES = (STATUS_PENDING, STATUS_SUBMITTED, STATUS_LOADED, STATUS_FAILED)

    ATTRIBUTION_MEMBER = "member"
    ATTRIBUTION_PI = "pi"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # AMIE Username; "" while the PI has no site login yet (never submitted).
    username: Mapped[str] = mapped_column(String, nullable=False)
    attribution: Mapped[str] = mapped_column(String, nullable=False)
    gpu_hours: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    charge: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    local_record_id: Mapped[str] = mapped_column(
        String, nullable=False, unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=STATUS_PENDING, index=True
    )
    submitted_charge: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    accounting_db_record_id: Mapped[str | None] = mapped_column(String, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    loaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project: Mapped["Project"] = relationship(
        "Project", back_populates="gpu_usage_records"
    )
