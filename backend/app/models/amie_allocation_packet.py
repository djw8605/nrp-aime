"""AMIE request_project_create packet details."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AMIEAllocationPacket(Base):
    """Parsed fields for ``request_project_create`` packets."""

    __tablename__ = "amie_allocation_packets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    packet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amie_packets.id"), unique=True, nullable=False
    )
    grant_number: Mapped[str] = mapped_column(String, index=True, nullable=False)
    record_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    project_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    resource: Mapped[str | None] = mapped_column(String, nullable=True)
    allocated_resource: Mapped[str | None] = mapped_column(String, nullable=True)
    allocation_type: Mapped[str] = mapped_column(String, nullable=False)
    request_type: Mapped[str | None] = mapped_column(String, nullable=True)
    service_units_allocated: Mapped[str] = mapped_column(String, nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    project_title: Mapped[str | None] = mapped_column(String, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    board_type: Mapped[str | None] = mapped_column(String, nullable=True)
    charge_number: Mapped[str | None] = mapped_column(String, nullable=True)
    pfos_number: Mapped[str] = mapped_column(String, nullable=False)
    proposal_number: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_person_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_global_id: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_first_name: Mapped[str] = mapped_column(String, nullable=False)
    pi_middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_last_name: Mapped[str] = mapped_column(String, nullable=False)
    pi_email: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_title: Mapped[str | None] = mapped_column(String, nullable=True)
    pi_organization: Mapped[str] = mapped_column(String, nullable=False)
    pi_org_code: Mapped[str] = mapped_column(String, nullable=False)
    sfos: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    academic_degree: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    role_list: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    pi_dn_list: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    pi_requested_login_list: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    site_person_ids: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    raw_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    packet: Mapped["AMIEPacket"] = relationship(
        "AMIEPacket", back_populates="allocation_packet"
    )
