"""Parsed details for non-allocation/non-account AMIE lifecycle packets."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AMIELifecyclePacket(Base):
    """Stores parsed metadata for lifecycle and maintenance packet types."""

    __tablename__ = "amie_lifecycle_packets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    packet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("amie_packets.id"), unique=True, nullable=False
    )
    packet_type: Mapped[str] = mapped_column(String, index=True, nullable=False)
    project_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    person_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    keep_person_id: Mapped[str | None] = mapped_column(String, nullable=True)
    delete_person_id: Mapped[str | None] = mapped_column(String, nullable=True)
    action_type: Mapped[str | None] = mapped_column(String, nullable=True)
    resource: Mapped[str | None] = mapped_column(String, nullable=True)
    dn_list: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    status_code: Mapped[str | None] = mapped_column(String, nullable=True)
    detail_code: Mapped[str | None] = mapped_column(String, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    packet: Mapped["AMIEPacket"] = relationship(
        "AMIEPacket", back_populates="lifecycle_packet"
    )
