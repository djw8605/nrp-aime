"""AMIE request_account_create packet details."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AMIENewUserPacket(Base):
    """Parsed fields for ``request_account_create`` packets."""

    __tablename__ = "amie_new_user_packets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    packet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amie_packets.id"), unique=True, nullable=False
    )
    grant_number: Mapped[str] = mapped_column(String, index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    resource: Mapped[str | None] = mapped_column(String, nullable=True)
    allocated_resource: Mapped[str | None] = mapped_column(String, nullable=True)
    user_person_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    user_global_id: Mapped[str | None] = mapped_column(String, nullable=True)
    user_first_name: Mapped[str] = mapped_column(String, nullable=False)
    user_middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    user_last_name: Mapped[str] = mapped_column(String, nullable=False)
    user_organization: Mapped[str] = mapped_column(String, nullable=False)
    user_org_code: Mapped[str] = mapped_column(String, nullable=False)
    user_title: Mapped[str | None] = mapped_column(String, nullable=True)
    user_department: Mapped[str | None] = mapped_column(String, nullable=True)
    user_city: Mapped[str | None] = mapped_column(String, nullable=True)
    user_state: Mapped[str | None] = mapped_column(String, nullable=True)
    user_country: Mapped[str | None] = mapped_column(String, nullable=True)
    user_street_address: Mapped[str | None] = mapped_column(String, nullable=True)
    user_street_address2: Mapped[str | None] = mapped_column(String, nullable=True)
    user_zip: Mapped[str | None] = mapped_column(String, nullable=True)
    user_email: Mapped[str | None] = mapped_column(String, nullable=True)
    user_business_phone_number: Mapped[str | None] = mapped_column(String, nullable=True)
    user_remote_site_login: Mapped[str | None] = mapped_column(String, nullable=True)
    user_password_access_enable: Mapped[str | None] = mapped_column(String, nullable=True)
    nsf_status_code: Mapped[str | None] = mapped_column(String, nullable=True)
    role_list: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    user_dn_list: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    user_requested_login_list: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    site_person_ids: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list
    )
    raw_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    packet: Mapped["AMIEPacket"] = relationship("AMIEPacket", back_populates="new_user_packet")
