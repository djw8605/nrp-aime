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

from app.config import settings
from app.database import SessionLocal
from app.services.account_lifecycle import AccountLifecycleService
from app.services.aime.service import AIMEService
from app.services.observability import ObservabilityService
from app.services.worker_status import WorkerStatusService

logger = logging.getLogger(__name__)
WORKER_NAME = "aime-worker"


def _packet_to_dict(packet: Any) -> dict[str, Any]:
    """Convert AMIE packet object or dict payload into dict form."""
    if isinstance(packet, dict):
        return packet
    if hasattr(packet, "as_dict"):
        return packet.as_dict()
    return {"raw": repr(packet)}


def process_packets(
    aime_svc: AIMEService, amie_client: AMIEClient, packets: list[Any]
) -> None:
    """Persist incoming packets to the database."""
    with SessionLocal() as db:
        for packet in packets:
            packet_payload = _packet_to_dict(packet)
            header = packet_payload.get("header", {})
            packet_rec_id = getattr(packet, "packet_rec_id", None) or header.get(
                "packet_rec_id"
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
                if result.project is not None:
                    logger.info("Ingested packet for project: %s", result.project.name)

                if result.handled and packet_rec_id is not None:
                    amie_client.set_packet_client_state(
                        packet_rec_id, settings.amie_processed_client_state
                    )
                elif not result.handled:
                    logger.debug(
                        "Packet received but not processed: %s",
                        result.packet_type,
                    )
            except Exception as exc:  # noqa: BLE001
                db.rollback()
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


def reconcile_accounts(lifecycle_svc: AccountLifecycleService) -> dict[str, int]:
    """Reconcile account lifecycle state from Authentik checks."""
    with SessionLocal() as db:
        return lifecycle_svc.reconcile_with_authentik(db)


def run_worker(poll_interval: int = 60) -> None:
    """Poll AMIE for new packets indefinitely.

    Args:
        poll_interval: Seconds to wait between polling cycles.
    """
    if not settings.amie_api_key:
        logger.warning(
            "AMIE_API_KEY is not configured; worker will idle until configured."
        )

    aime_svc = AIMEService(site_name=settings.amie_site_name)
    lifecycle_svc = AccountLifecycleService()
    logger.info("AIME worker started (site=%s)", settings.amie_site_name)
    amie_client = AMIEClient(
        site_name=settings.amie_site_name,
        api_key=settings.amie_api_key,
        amie_url=settings.amie_url,
    )

    _update_worker_status(
        is_active=True,
        current_state="starting",
        status_message="worker starting",
    )

    try:
        while True:
            if not settings.amie_api_key:
                try:
                    sync_result = reconcile_accounts(lifecycle_svc)
                except Exception:  # noqa: BLE001
                    logger.exception("Account reconciliation failed")
                    sync_result = {"checked": 0, "transitioned": 0, "confirmations_sent": 0, "failures": 1}
                _update_worker_status(
                    is_active=True,
                    current_state="waiting_for_api_key",
                    status_message="AMIE_API_KEY is not configured",
                    state_payload={"account_sync": sync_result},
                )
                time.sleep(poll_interval)
                continue

            try:
                _update_worker_status(
                    is_active=True,
                    current_state="polling",
                    status_message="polling AMIE for incoming packets",
                )
                packets = amie_client.list_packets(incoming=True).packets
                packet_count = len(packets)
                now_iso = datetime.now(UTC).isoformat()
                if packet_count:
                    _update_worker_status(
                        is_active=True,
                        current_state="processing_packets",
                        status_message="processing incoming AMIE packets",
                        state_payload={"packet_count": packet_count},
                    )
                    process_packets(aime_svc, amie_client, packets)

                sync_result = reconcile_accounts(lifecycle_svc)

                _update_worker_status(
                    is_active=True,
                    current_state="idle",
                    status_message="poll cycle completed",
                    state_payload={
                        "last_poll_packet_count": packet_count,
                        "last_successful_poll_at": now_iso,
                        "last_successful_authentik_reconcile_at": now_iso,
                        "account_sync": sync_result,
                    },
                    mark_success=True,
                )
                with SessionLocal() as alert_db:
                    ObservabilityService.evaluate_alerts(alert_db)
            except Exception as exc:  # noqa: BLE001
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
