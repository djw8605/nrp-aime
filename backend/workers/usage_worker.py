"""AMIE usage export worker.

Collects current project usage from Prometheus and sends usage records to
the AMIE Usage API.
"""

import logging
import time
from datetime import UTC, datetime

from app.config import settings
from app.database import SessionLocal
from app.services.aime.usage_service import AMIEUsageService
from app.services.observability import ObservabilityService
from app.services.worker_status import WorkerStatusService

logger = logging.getLogger(__name__)
WORKER_NAME = "usage-worker"


def _update_worker_status(
    *,
    is_active: bool,
    current_state: str,
    status_message: str | None = None,
    state_payload: dict | None = None,
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


def run_worker(poll_interval: int | None = None) -> None:
    """Run usage export loop indefinitely."""
    interval_seconds = poll_interval or (settings.amie_usage_interval_minutes * 60)
    usage_svc = AMIEUsageService()

    if not settings.amie_api_key:
        logger.warning("AMIE_API_KEY is not configured; usage worker will idle.")

    logger.info(
        "AMIE usage worker started (site=%s usage_url=%s interval=%ss)",
        settings.amie_site_name,
        settings.amie_usage_url,
        interval_seconds,
    )

    _update_worker_status(
        is_active=True,
        current_state="starting",
        status_message="worker starting",
    )

    try:
        while True:
            try:
                if settings.amie_api_key:
                    _update_worker_status(
                        is_active=True,
                        current_state="sending_usage",
                        status_message="sending AMIE usage records",
                    )
                    with SessionLocal() as db:
                        result = usage_svc.send_all_projects_usage(db)
                    now_iso = datetime.now(UTC).isoformat()
                    _update_worker_status(
                        is_active=True,
                        current_state="idle",
                        status_message="usage export cycle completed",
                        state_payload={
                            **result,
                            "last_successful_usage_export_at": now_iso,
                        },
                        mark_success=True,
                    )
                    with SessionLocal() as alert_db:
                        ObservabilityService.evaluate_alerts(alert_db)
                else:
                    _update_worker_status(
                        is_active=True,
                        current_state="waiting_for_api_key",
                        status_message="AMIE_API_KEY is not configured",
                    )
            except Exception as exc:  # noqa: BLE001
                _update_worker_status(
                    is_active=True,
                    current_state="error",
                    status_message=str(exc),
                    mark_error=True,
                )
                logger.exception("AMIE usage worker error")

            time.sleep(interval_seconds)
    finally:
        _update_worker_status(
            is_active=False,
            current_state="stopped",
            status_message="worker stopped",
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
