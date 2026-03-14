"""Schemas for packet log endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PacketLogRead(BaseModel):
    """Read schema for one packet log row."""

    id: uuid.UUID
    packet_rec_id: int | None
    trans_rec_id: int | None
    transaction_id: int | None
    packet_type: str
    processing_status: str
    processed: bool
    processing_error: str | None
    raw_packet: dict[str, Any]
    received_at: datetime
    processed_at: datetime | None


class PacketLogPage(BaseModel):
    """Paged packet log response."""

    items: list[PacketLogRead]
    total: int
    page: int
    page_size: int
