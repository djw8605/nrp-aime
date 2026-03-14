"""Packet log API endpoints."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Text, cast, func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.amie_packet import AMIEPacket
from app.schemas.packets import PacketLogPage, PacketLogRead

router = APIRouter()

SortBy = Literal[
    "received_at",
    "processed_at",
    "packet_type",
    "packet_rec_id",
    "trans_rec_id",
    "transaction_id",
    "processing_status",
]
SortOrder = Literal["asc", "desc"]


def _to_read_model(packet: AMIEPacket) -> PacketLogRead:
    """Convert ORM row to API response model."""
    status = packet.processing_status or AMIEPacket.PROCESSING_STATUS_RECEIVED
    return PacketLogRead(
        id=packet.id,
        packet_rec_id=packet.packet_rec_id,
        trans_rec_id=packet.trans_rec_id,
        transaction_id=packet.transaction_id,
        packet_type=packet.packet_type,
        processing_status=status,
        processed=status == AMIEPacket.PROCESSING_STATUS_PROCESSED,
        processing_error=packet.processing_error,
        raw_packet=packet.raw_packet,
        received_at=packet.created_at,
        processed_at=packet.processed_at,
    )


@router.get("/logs", response_model=PacketLogPage)
def list_packet_logs(
    *,
    db: Session = Depends(get_db),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    sort_by: SortBy = Query(default="received_at"),
    sort_order: SortOrder = Query(default="desc"),
    q: str | None = Query(default=None, description="Search string"),
    status: str | None = Query(default=None, description="Filter by processing status"),
) -> PacketLogPage:
    """Return packet logs with paging, sorting, and search."""
    query = db.query(AMIEPacket)

    if status:
        query = query.filter(
            func.lower(AMIEPacket.processing_status) == status.strip().lower()
        )

    search_term = (q or "").strip()
    if search_term:
        pattern = f"%{search_term}%"
        query = query.filter(
            or_(
                AMIEPacket.packet_type.ilike(pattern),
                AMIEPacket.processing_status.ilike(pattern),
                cast(AMIEPacket.packet_rec_id, Text).ilike(pattern),
                cast(AMIEPacket.trans_rec_id, Text).ilike(pattern),
                cast(AMIEPacket.transaction_id, Text).ilike(pattern),
                cast(AMIEPacket.raw_packet, Text).ilike(pattern),
            )
        )

    sort_column_map = {
        "received_at": AMIEPacket.created_at,
        "processed_at": AMIEPacket.processed_at,
        "packet_type": AMIEPacket.packet_type,
        "packet_rec_id": AMIEPacket.packet_rec_id,
        "trans_rec_id": AMIEPacket.trans_rec_id,
        "transaction_id": AMIEPacket.transaction_id,
        "processing_status": AMIEPacket.processing_status,
    }
    sort_column = sort_column_map.get(sort_by, AMIEPacket.created_at)
    order_clause = (
        sort_column.asc().nullslast()
        if sort_order == "asc"
        else sort_column.desc().nullslast()
    )

    total = query.count()
    rows = (
        query.order_by(order_clause, AMIEPacket.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PacketLogPage(
        items=[_to_read_model(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
