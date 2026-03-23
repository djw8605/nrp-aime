"""Schemas for packet log endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


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


class EntityPacketRead(BaseModel):
    """Compact packet reference for entity detail pages."""

    id: uuid.UUID
    packet_rec_id: int | None
    trans_rec_id: int | None
    transaction_id: int | None
    packet_type: str
    processing_status: str
    processing_error: str | None = None
    ingest_source: str
    received_at: datetime
    processed_at: datetime | None = None
    matched_on: list[str] = Field(default_factory=list)


class PacketLogPage(BaseModel):
    """Paged packet log response."""

    items: list[PacketLogRead]
    total: int
    page: int
    page_size: int


class ManualPacketCreate(BaseModel):
    """Schema for manually ingesting a packet from admin input."""

    packet_type: str = Field(min_length=1)
    packet_rec_id: int
    trans_rec_id: int | None = None
    packet_id: int | None = None
    transaction_id: int | None = None
    packet_timestamp: datetime | None = None
    local_site_name: str | None = None
    remote_site_name: str | None = None
    originating_site_name: str | None = None
    outgoing_flag: bool | None = None
    transaction_state: str | None = None
    packet_state: str | None = None
    client_state: str | None = None
    body: dict[str, Any] = Field(default_factory=dict)

    def to_packet_dict(self) -> dict[str, Any]:
        """Build packet dictionary expected by the ingestion service."""
        header = {
            "packet_rec_id": self.packet_rec_id,
            "trans_rec_id": self.trans_rec_id,
            "packet_id": self.packet_id,
            "transaction_id": self.transaction_id,
            "packet_timestamp": self.packet_timestamp,
            "local_site_name": self.local_site_name,
            "remote_site_name": self.remote_site_name,
            "originating_site_name": self.originating_site_name,
            "outgoing_flag": self.outgoing_flag,
            "transaction_state": self.transaction_state,
            "packet_state": self.packet_state,
            "client_state": self.client_state,
        }
        normalized_header = {k: v for k, v in header.items() if v is not None}
        return {
            "type": self.packet_type,
            "header": normalized_header,
            "body": self.body or {},
        }


class PacketValidationRequest(BaseModel):
    """Schema for packet dry-run validation."""

    raw_packet: dict[str, Any]


class PacketValidationResult(BaseModel):
    """Validation response for dry-run checks."""

    valid: bool
    packet_type: str
    bound_type: str | None = None
    errors: list[dict[str, Any]] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class PacketReprocessResult(BaseModel):
    """Schema for single packet reprocess/reingest result."""

    packet_id: uuid.UUID
    packet_rec_id: int | None
    handled: bool
    packet_type: str
    processing_status: str
    reprocess_attempt_count: int
    reprocess_locked_until: datetime | None = None
    detail: str | None = None


class TransactionSummaryRead(BaseModel):
    """Schema for transaction-centric view."""

    transaction_id: int
    trans_rec_id: int | None = None
    packet_count: int
    current_state: str
    pending_actions: list[str] = Field(default_factory=list)
    reply_eligible: bool = False
    packets: list[dict[str, Any]] = Field(default_factory=list)
