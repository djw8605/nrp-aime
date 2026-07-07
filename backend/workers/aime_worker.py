"""AIME background worker.

Polls the AMIE endpoint for incoming packets and delegates
processing to the :class:`~app.services.aime.service.AIMEService`.

This worker can be run as a standalone process::

    python -m workers.aime_worker

or integrated into a task queue such as Celery.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from amieclient import AMIEClient

from app.config import configured_amie_site_names, settings
from app.database import SessionLocal
from app.services.account_lifecycle import AccountLifecycleService
from app.services.aime.service import AIMEService
from app.services.observability import ObservabilityService
from app.services.worker_status import WorkerStatusService

logger = logging.getLogger(__name__)
WORKER_NAME = "aime-worker"


def _log_amie_interaction(action: str, **context: Any) -> None:
    """Emit a consistent INFO log line for AMIE API interactions."""
    details = ", ".join(f"{key}={value!r}" for key, value in sorted(context.items()))
    if details:
        logger.info("AMIE interaction action=%s %s", action, details)
    else:
        logger.info("AMIE interaction action=%s", action)


def _packet_to_dict(packet: Any) -> dict[str, Any]:
    """Convert AMIE packet object or dict payload into dict form."""
    if isinstance(packet, dict):
        return packet
    if hasattr(packet, "as_dict"):
        return packet.as_dict()
    return {"raw": repr(packet)}


def process_packets(
    aime_svc: AIMEService, amie_client: AMIEClient, packets: list[Any], *, site_name: str
) -> None:
    """Persist incoming packets to the database."""
    with SessionLocal() as db:
        for packet in packets:
            packet_payload = _packet_to_dict(packet)
            header = packet_payload.get("header", {})
            packet_rec_id = getattr(packet, "packet_rec_id", None) or header.get(
                "packet_rec_id"
            )
            outgoing_flag = header.get("outgoing_flag")
            is_outgoing = str(outgoing_flag).strip().lower() in {"1", "true", "yes"}
            _log_amie_interaction(
                "ingest_packet.start",
                site_name=site_name,
                packet_type=packet_payload.get("type"),
                packet_rec_id=packet_rec_id,
                trans_rec_id=header.get("trans_rec_id"),
                is_outgoing=is_outgoing,
            )
            logger.debug(
                "Received AMIE packet type=%s packet_rec_id=%s trans_rec_id=%s payload=%s",
                packet_payload.get("type"),
                header.get("packet_rec_id", packet_rec_id),
                header.get("trans_rec_id"),
                packet_payload,
            )
            try:
                result = aime_svc.ingest_packet(db, packet)
                _log_amie_interaction(
                    "ingest_packet.finish",
                    site_name=site_name,
                    packet_type=result.packet_type,
                    packet_rec_id=packet_rec_id,
                    handled=result.handled,
                    accepted=getattr(result, "accepted", None),
                    skipped=getattr(result, "skipped", None),
                )
                if result.project is not None:
                    logger.info("Ingested packet for project: %s", result.project.name)

                if result.handled and packet_rec_id is not None and not is_outgoing:
                    _log_amie_interaction(
                        "set_packet_client_state.start",
                        site_name=site_name,
                        packet_rec_id=packet_rec_id,
                        client_state=settings.amie_processed_client_state,
                    )
                    amie_client.set_packet_client_state(
                        packet_rec_id, settings.amie_processed_client_state
                    )
                    _log_amie_interaction(
                        "set_packet_client_state.finish",
                        site_name=site_name,
                        packet_rec_id=packet_rec_id,
                        client_state=settings.amie_processed_client_state,
                    )
                elif not result.handled:
                    logger.debug(
                        "Packet received but not processed: %s",
                        result.packet_type,
                    )
                elif is_outgoing:
                    _log_amie_interaction(
                        "set_packet_client_state.skipped_outgoing",
                        site_name=site_name,
                        packet_rec_id=packet_rec_id,
                    )
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                _log_amie_interaction(
                    "ingest_packet.error",
                    site_name=site_name,
                    packet_rec_id=packet_rec_id,
                    error=str(exc),
                )
                logger.exception("Failed to ingest packet %s", packet_rec_id)
                aime_svc.mark_packet_error(
                    db,
                    packet_payload,
                    error_message=f"Failed to ingest packet {packet_rec_id}: {exc}",
                )


def _update_worker_status(
    *,
    is_active: bool,
    current_state: str,
    status_message: str | None = None,
    state_payload: dict[str, Any] | None = None,
    mark_success: bool = False,
    mark_error: bool = False,
) -> None:
    """Write worker heartbeat/state to DB."""
    try:
        with SessionLocal() as db:
            WorkerStatusService.update_status(
                db,
                worker_name=WORKER_NAME,
                is_active=is_active,
                current_state=current_state,
                status_message=status_message,
                state_payload=state_payload,
                mark_success=mark_success,
                mark_error=mark_error,
            )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to update %s status", WORKER_NAME)


def sync_account_confirmations(lifecycle_svc: AccountLifecycleService) -> dict[str, int]:
    """Sync pending account confirmations to AIME."""
    with SessionLocal() as db:
        return lifecycle_svc.reconcile_pending_confirmations(db)


def sync_project_notifications(lifecycle_svc: AccountLifecycleService) -> dict[str, int]:
    """Sync pending notify_project_create packets to AIME."""
    with SessionLocal() as db:
        return lifecycle_svc.reconcile_pending_project_notifications(db)


def sync_lifecycle_notifications(
    lifecycle_svc: AccountLifecycleService,
) -> dict[str, int]:
    """Sync pending notify_(project|account)_(in|re)activate replies to AIME."""
    with SessionLocal() as db:
        return lifecycle_svc.reconcile_pending_lifecycle_notifications(db)


def run_worker(poll_interval: int = 60) -> None:
    """Poll AMIE for new packets indefinitely.

    Args:
        poll_interval: Seconds to wait between polling cycles.
    """
    if not settings.amie_api_key:
        logger.warning(
            "AMIE_API_KEY is not configured; worker will idle until configured."
        )

    site_names = configured_amie_site_names()
    aime_services = {
        site_name: AIMEService(site_name=site_name) for site_name in site_names
    }
    lifecycle_svc = AccountLifecycleService()
    logger.info("AIME worker started (sites=%s)", ", ".join(site_names))
    _log_amie_interaction(
        "worker.start",
        site_names=",".join(site_names),
        poll_interval_seconds=poll_interval,
        amie_url=settings.amie_url,
    )
    amie_clients = {
        site_name: AMIEClient(
            site_name=site_name,
            api_key=settings.amie_api_key,
            amie_url=settings.amie_url,
        )
        for site_name in site_names
    }

    _update_worker_status(
        is_active=True,
        current_state="starting",
        status_message="worker starting",
    )

    try:
        while True:
            if not settings.amie_api_key:
                _update_worker_status(
                    is_active=True,
                    current_state="waiting_for_api_key",
                    status_message="AMIE_API_KEY is not configured",
                )
                time.sleep(poll_interval)
                continue

            try:
                cycle_started_at = datetime.now(UTC).isoformat()
                _log_amie_interaction(
                    "poll_cycle.start",
                    started_at=cycle_started_at,
                    site_count=len(site_names),
                )
                _update_worker_status(
                    is_active=True,
                    current_state="polling",
                    status_message="polling AMIE for incoming/outgoing packets",
                )
                site_packet_counts: dict[str, int] = {}
                site_incoming_counts: dict[str, int] = {}
                site_outgoing_counts: dict[str, int] = {}
                packet_count = 0
                for site_name in site_names:
                    _log_amie_interaction(
                        "list_packets.start",
                        site_name=site_name,
                        incoming=True,
                    )
                    incoming_packets = amie_clients[site_name].list_packets(
                        incoming=True
                    ).packets
                    _log_amie_interaction(
                        "list_packets.finish",
                        site_name=site_name,
                        incoming=True,
                        packet_count=len(incoming_packets),
                    )
                    _log_amie_interaction(
                        "list_packets.start",
                        site_name=site_name,
                        incoming=False,
                    )
                    outgoing_packets = amie_clients[site_name].list_packets(
                        incoming=False
                    ).packets
                    _log_amie_interaction(
                        "list_packets.finish",
                        site_name=site_name,
                        incoming=False,
                        packet_count=len(outgoing_packets),
                    )
                    by_packet_rec_id: dict[Any, Any] = {}
                    passthrough_packets: list[Any] = []
                    for pkt in [*incoming_packets, *outgoing_packets]:
                        payload = _packet_to_dict(pkt)
                        header = payload.get("header", {})
                        key = getattr(pkt, "packet_rec_id", None) or header.get(
                            "packet_rec_id"
                        )
                        if key is None:
                            passthrough_packets.append(pkt)
                            continue
                        by_packet_rec_id[key] = pkt
                    packets = list(by_packet_rec_id.values()) + passthrough_packets
                    site_count = len(packets)
                    site_incoming_counts[site_name] = len(incoming_packets)
                    site_outgoing_counts[site_name] = len(outgoing_packets)
                    site_packet_counts[site_name] = site_count
                    packet_count += site_count
                    if site_count:
                        _update_worker_status(
                            is_active=True,
                            current_state="processing_packets",
                            status_message=(
                                f"processing AMIE packets (site={site_name})"
                            ),
                            state_payload={
                                "site": site_name,
                                "site_incoming_packet_count": len(incoming_packets),
                                "site_outgoing_packet_count": len(outgoing_packets),
                                "site_packet_count": site_count,
                            },
                        )
                        process_packets(
                            aime_services[site_name],
                            amie_clients[site_name],
                            packets,
                            site_name=site_name,
                        )

                now_iso = datetime.now(UTC).isoformat()
                _log_amie_interaction(
                    "reconcile_pending_confirmations.start",
                    at=now_iso,
                )
                sync_result = sync_account_confirmations(lifecycle_svc)
                _log_amie_interaction(
                    "reconcile_pending_confirmations.finish",
                    at=now_iso,
                    checked=sync_result.get("checked"),
                    transitioned=sync_result.get("transitioned"),
                    confirmations_sent=sync_result.get("confirmations_sent"),
                    failures=sync_result.get("failures"),
                    deferred=sync_result.get("deferred"),
                )

                _log_amie_interaction(
                    "reconcile_pending_project_notifications.start",
                    at=now_iso,
                )
                proj_result = sync_project_notifications(lifecycle_svc)
                _log_amie_interaction(
                    "reconcile_pending_project_notifications.finish",
                    at=now_iso,
                    checked=proj_result.get("checked"),
                    notifications_sent=proj_result.get("notifications_sent"),
                    already_sent=proj_result.get("already_sent"),
                    failures=proj_result.get("failures"),
                    deferred=proj_result.get("deferred"),
                )

                _log_amie_interaction(
                    "reconcile_pending_lifecycle_notifications.start",
                    at=now_iso,
                )
                lifecycle_result = sync_lifecycle_notifications(lifecycle_svc)
                _log_amie_interaction(
                    "reconcile_pending_lifecycle_notifications.finish",
                    at=now_iso,
                    checked=lifecycle_result.get("checked"),
                    notifications_sent=lifecycle_result.get("notifications_sent"),
                    already_sent=lifecycle_result.get("already_sent"),
                    failures=lifecycle_result.get("failures"),
                    deferred=lifecycle_result.get("deferred"),
                )

                _update_worker_status(
                    is_active=True,
                    current_state="idle",
                    status_message="poll cycle completed",
                    state_payload={
                        "last_poll_packet_count": packet_count,
                        "site_packet_counts": site_packet_counts,
                        "site_incoming_packet_counts": site_incoming_counts,
                        "site_outgoing_packet_counts": site_outgoing_counts,
                        "sites_polled": site_names,
                        "last_successful_poll_at": now_iso,
                        "last_successful_account_confirmation_sync_at": now_iso,
                        "account_confirmation_sync": sync_result,
                        "project_notification_sync": proj_result,
                        "lifecycle_notification_sync": lifecycle_result,
                    },
                    mark_success=True,
                )
                _log_amie_interaction(
                    "poll_cycle.finish",
                    started_at=cycle_started_at,
                    completed_at=now_iso,
                    total_packets=packet_count,
                    site_packet_counts=site_packet_counts,
                )
                with SessionLocal() as alert_db:
                    ObservabilityService.evaluate_alerts(alert_db)
            except Exception as exc:  # noqa: BLE001
                _log_amie_interaction("poll_cycle.error", error=str(exc))
                _update_worker_status(
                    is_active=True,
                    current_state="error",
                    status_message=str(exc),
                    mark_error=True,
                )
                logger.exception("AIME worker error")

            time.sleep(poll_interval)
    finally:
        _update_worker_status(
            is_active=False,
            current_state="stopped",
            status_message="worker stopped",
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
