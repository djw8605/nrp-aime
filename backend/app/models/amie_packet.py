"""AMIE packet envelope model."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AMIEPacket(Base):
    """Stores packet metadata and raw payload for dedupe/auditing."""

    __tablename__ = "amie_packets"
    PROCESSING_STATUS_RECEIVED = "received"
    PROCESSING_STATUS_PROCESSED = "processed"
    PROCESSING_STATUS_UNPROCESSED = "unprocessed"
    PROCESSING_STATUS_ERROR = "error"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    packet_rec_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    trans_rec_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    packet_id: Mapped[int | None] = mapped_column(BigInteger)
    transaction_id: Mapped[int | None] = mapped_column(BigInteger)
    packet_type: Mapped[str] = mapped_column(String, index=True, nullable=False)
    local_site_name: Mapped[str | None] = mapped_column(String, nullable=True)
    remote_site_name: Mapped[str | None] = mapped_column(String, nullable=True)
    originating_site_name: Mapped[str | None] = mapped_column(String, nullable=True)
    outgoing_flag: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    transaction_state: Mapped[str | None] = mapped_column(String, nullable=True)
    packet_state: Mapped[str | None] = mapped_column(String, nullable=True)
    client_state: Mapped[str | None] = mapped_column(String, nullable=True)
    packet_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_status: Mapped[str] = mapped_column(
        String,
        index=True,
        nullable=False,
        default=PROCESSING_STATUS_RECEIVED,
        server_default=text("'received'"),
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    raw_packet: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    allocation_packet: Mapped["AMIEAllocationPacket | None"] = relationship(
        "AMIEAllocationPacket", back_populates="packet", uselist=False
    )
    lifecycle_packet: Mapped["AMIELifecyclePacket | None"] = relationship(
        "AMIELifecyclePacket", back_populates="packet", uselist=False
    )
    new_user_packet: Mapped["AMIENewUserPacket | None"] = relationship(
        "AMIENewUserPacket", back_populates="packet", uselist=False
    )
