"""Packet log, reprocess, validation, and transaction API endpoints."""

from datetime import UTC, datetime, timedelta
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Text, cast, func, or_
from sqlalchemy.orm import Session

from app.config import configured_amie_site_names, settings
from app.database import get_db
from app.models.amie_packet import AMIEPacket
from app.schemas.packets import (
    ManualPacketCreate,
    PacketLogPage,
    PacketLogRead,
    PacketReprocessResult,
    PacketValidationRequest,
    PacketValidationResult,
    TransactionSummaryRead,
)
from app.services.aime.service import AIMEService
from app.services.observability import ObservabilityService

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


def _default_aime_site_name() -> str:
    return configured_amie_site_names()[0]


def _to_read_model(packet: AMIEPacket) -> PacketLogRead:
    """Convert ORM row to API response model."""
    status = packet.processing_status or AMIEPacket.PROCESSING_STATUS_RECEIVED
    return PacketLogRead(
        id=packet.id,
        packet_rec_id=packet.packet_rec_id,
        trans_rec_id=packet.trans_rec_id,
        transaction_id=packet.transaction_id,
        packet_type=packet.packet_type,
        outgoing_flag=packet.outgoing_flag,
        processing_status=status,
        processed=status == AMIEPacket.PROCESSING_STATUS_PROCESSED,
        processing_error=packet.processing_error,
        raw_packet=packet.raw_packet,
        received_at=packet.created_at,
        processed_at=packet.processed_at,
    )


def _reprocess_lock(packet: AMIEPacket) -> datetime:
    return datetime.now(UTC) + timedelta(
        minutes=max(1, settings.amie_packet_reprocess_lockout_minutes)
    )


def _set_reprocess_failure(packet: AMIEPacket, *, message: str) -> None:
    packet.reprocess_attempt_count = int(packet.reprocess_attempt_count or 0) + 1
    packet.reprocess_last_attempt_at = datetime.now(UTC)
    packet.reprocess_last_error = message
    if packet.reprocess_attempt_count >= settings.amie_packet_reprocess_max_retries:
        packet.reprocess_locked_until = _reprocess_lock(packet)


def _ensure_reprocess_allowed(packet: AMIEPacket) -> None:
    now = datetime.now(UTC)
    if packet.reprocess_locked_until and packet.reprocess_locked_until > now:
        raise HTTPException(
            status_code=423,
            detail=(
                "Packet reprocess is locked until "
                f"{packet.reprocess_locked_until.isoformat()}"
            ),
        )


def _run_reingest(
    db: Session,
    *,
    packet: AMIEPacket,
    aime_svc: AIMEService,
) -> PacketReprocessResult:
    _ensure_reprocess_allowed(packet)
    try:
        result = aime_svc.ingest_packet(
            db,
            packet.raw_packet,
            ingest_source=AMIEPacket.INGEST_SOURCE_REPROCESS,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        refreshed = db.query(AMIEPacket).filter(AMIEPacket.id == packet.id).first()
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Packet log entry not found") from exc
        _set_reprocess_failure(refreshed, message=f"Re-ingest failed: {exc}")
        db.commit()
        return PacketReprocessResult(
            packet_id=refreshed.id,
            packet_rec_id=refreshed.packet_rec_id,
            handled=False,
            packet_type=refreshed.packet_type,
            processing_status=refreshed.processing_status,
            reprocess_attempt_count=int(refreshed.reprocess_attempt_count or 0),
            reprocess_locked_until=refreshed.reprocess_locked_until,
            detail=str(exc),
        )

    refreshed = db.query(AMIEPacket).filter(AMIEPacket.id == packet.id).first()
    if refreshed is None:
        raise HTTPException(status_code=404, detail="Packet log entry not found")

    if result.handled:
        refreshed.reprocess_attempt_count = 0
        refreshed.reprocess_last_error = None
        refreshed.reprocess_last_attempt_at = datetime.now(UTC)
        refreshed.reprocess_locked_until = None
        db.commit()
        return PacketReprocessResult(
            packet_id=refreshed.id,
            packet_rec_id=refreshed.packet_rec_id,
            handled=True,
            packet_type=result.packet_type,
            processing_status=refreshed.processing_status,
            reprocess_attempt_count=int(refreshed.reprocess_attempt_count or 0),
            reprocess_locked_until=refreshed.reprocess_locked_until,
            detail="Packet re-ingested successfully",
        )

    _set_reprocess_failure(
        refreshed,
        message=f"Re-ingest did not handle packet type: {result.packet_type}",
    )
    db.commit()
    return PacketReprocessResult(
        packet_id=refreshed.id,
        packet_rec_id=refreshed.packet_rec_id,
        handled=False,
        packet_type=result.packet_type,
        processing_status=refreshed.processing_status,
        reprocess_attempt_count=int(refreshed.reprocess_attempt_count or 0),
        reprocess_locked_until=refreshed.reprocess_locked_until,
        detail="Packet re-ingested but remained unhandled",
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
    direction: str | None = Query(
        default=None,
        description="Filter by direction: 'incoming', 'outgoing', or omit for all",
    ),
) -> PacketLogPage:
    """Return packet logs with paging, sorting, and search."""
    query = db.query(AMIEPacket)

    if status:
        query = query.filter(
            func.lower(AMIEPacket.processing_status) == status.strip().lower()
        )

    if direction:
        direction_lower = direction.strip().lower()
        if direction_lower == "outgoing":
            query = query.filter(AMIEPacket.outgoing_flag.is_(True))
        elif direction_lower == "incoming":
            query = query.filter(
                or_(AMIEPacket.outgoing_flag.is_(False), AMIEPacket.outgoing_flag.is_(None))
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


@router.get("/logs/{packet_id}", response_model=PacketLogRead)
def get_packet_log(
    packet_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> PacketLogRead:
    """Return one packet log row by primary key."""
    row = db.query(AMIEPacket).filter(AMIEPacket.id == packet_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Packet log entry not found")
    return _to_read_model(row)


@router.post("/validate", response_model=PacketValidationResult)
def validate_packet(
    payload: PacketValidationRequest,
    db: Session = Depends(get_db),
) -> PacketValidationResult:
    """Validate packet shape/type against supported bindings without ingesting."""
    _ = db  # keeps endpoint signature consistent for future DB-aware checks
    aime_svc = AIMEService(site_name=_default_aime_site_name())
    result = aime_svc.validate_packet_dry_run(payload.raw_packet)
    return PacketValidationResult(**result)


@router.post("/manual", response_model=PacketLogRead)
def ingest_manual_packet(
    payload: ManualPacketCreate,
    db: Session = Depends(get_db),
) -> PacketLogRead:
    """Manually ingest a packet from admin-entered fields."""
    packet_dict = payload.to_packet_dict()
    aime_svc = AIMEService(site_name=_default_aime_site_name())

    try:
        result = aime_svc.ingest_packet(
            db,
            packet_dict,
            ingest_source=AMIEPacket.INGEST_SOURCE_MANUAL,
        )
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        aime_svc.mark_packet_error(
            db,
            packet_dict,
            error_message=f"Manual packet ingest failed: {exc}",
            ingest_source=AMIEPacket.INGEST_SOURCE_MANUAL,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Manual packet ingest failed: {exc}",
        ) from exc

    row = (
        db.query(AMIEPacket)
        .filter(AMIEPacket.packet_rec_id == payload.packet_rec_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=500,
            detail="Manual packet ingest completed but packet log row is missing",
        )

    if not result.handled:
        raise HTTPException(
            status_code=400,
            detail=f"Manual packet was saved but is not supported: {result.packet_type}",
        )

    return _to_read_model(row)


@router.post("/logs/{packet_id}/reingest", response_model=PacketReprocessResult)
def reingest_packet(
    packet_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> PacketReprocessResult:
    """Re-ingest one packet from packet log, with retry lockouts."""
    row = db.query(AMIEPacket).filter(AMIEPacket.id == packet_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Packet log entry not found")
    site_name = (
        row.remote_site_name
        or row.originating_site_name
        or row.local_site_name
        or _default_aime_site_name()
    )
    aime_svc = AIMEService(site_name=site_name)
    return _run_reingest(db, packet=row, aime_svc=aime_svc)


@router.get("/transactions/{transaction_id}", response_model=TransactionSummaryRead)
def get_transaction_summary(
    transaction_id: int,
    db: Session = Depends(get_db),
) -> TransactionSummaryRead:
    """Return transaction-centric packet state and reply eligibility."""
    summary = ObservabilityService.transaction_summary(db, transaction_id)
    return TransactionSummaryRead(**summary)


@router.post("/transactions/{transaction_id}/replay")
def replay_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """Replay all packets in a transaction through ingest pipeline."""
    rows = (
        db.query(AMIEPacket)
        .filter(AMIEPacket.transaction_id == transaction_id)
        .order_by(AMIEPacket.created_at.asc())
        .all()
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Transaction not found")

    results: list[PacketReprocessResult] = []
    for row in rows:
        site_name = (
            row.remote_site_name
            or row.originating_site_name
            or row.local_site_name
            or _default_aime_site_name()
        )
        aime_svc = AIMEService(site_name=site_name)
        try:
            results.append(_run_reingest(db, packet=row, aime_svc=aime_svc))
        except HTTPException as exc:
            results.append(
                PacketReprocessResult(
                    packet_id=row.id,
                    packet_rec_id=row.packet_rec_id,
                    handled=False,
                    packet_type=row.packet_type,
                    processing_status=row.processing_status,
                    reprocess_attempt_count=int(row.reprocess_attempt_count or 0),
                    reprocess_locked_until=row.reprocess_locked_until,
                    detail=f"Skipped: {exc.detail}",
                )
            )

    handled = sum(1 for item in results if item.handled)
    failed = len(results) - handled
    return {
        "transaction_id": transaction_id,
        "packet_count": len(results),
        "handled": handled,
        "failed_or_skipped": failed,
        "results": [item.model_dump(mode="json") for item in results],
    }
