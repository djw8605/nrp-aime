"""Stores packets that failed to process."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AMIEUnprocessedPacket(Base):
    """Represents a packet that could not be processed."""

    __tablename__ = "amie_unprocessed_packets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    packet_fingerprint: Mapped[str] = mapped_column(String, unique=True, index=True)
    packet_rec_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    trans_rec_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    transaction_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    packet_type: Mapped[str | None] = mapped_column(String, index=True)
    failure_reason: Mapped[str] = mapped_column(String, index=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_packet: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
