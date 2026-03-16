"""Tracks outbound packets sent to AMIE and retry/ack state."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OutboundPacketLog(Base):
    """Persistent log of outbound packet delivery status."""

    __tablename__ = "outbound_packet_logs"

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_RETRYING = "retrying"
    STATUS_FAILED = "failed"
    STATUS_LOCKED = "locked"

    ACK_UNKNOWN = "unknown"
    ACK_PENDING = "pending"
    ACK_ACKED = "acked"
    ACK_NOT_ACKED = "not_acked"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    worker_name: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=STATUS_PENDING, index=True
    )
    ack_status: Mapped[str] = mapped_column(
        String, nullable=False, default=ACK_UNKNOWN, index=True
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
    outbound_packet_rec_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    outbound_transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    project_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("project_users.id"), nullable=True, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
