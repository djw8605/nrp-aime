"""GPU usage export worker.

Each cycle pulls daily GPU usage for GPU allocations from the NRP accounting
public API, records it in ``gpu_usage_records``, submits it to the ACCESS
Usage API, and reconciles what ACCESS has loaded.
"""

import logging
import time
from datetime import UTC, datetime

from app.config import settings
from app.database import SessionLocal
from app.services.gpu_accounting.service import GpuAccountingService
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


def _evaluate_alerts() -> None:
    with SessionLocal() as alert_db:
        ObservabilityService.evaluate_alerts(alert_db)


def run_once(service: GpuAccountingService) -> dict[str, int]:
    """Run one GPU accounting cycle and record worker status."""
    _update_worker_status(
        is_active=True,
        current_state="collecting_gpu_usage",
        status_message="collecting GPU usage and reporting to ACCESS",
    )
    with SessionLocal() as db:
        result = service.run_cycle(db)
    disabled_reason = service.submission_disabled_reason()
    state_payload: dict = dict(result)
    if disabled_reason is None:
        status_message = "GPU usage cycle completed"
        # Export freshness only advances when the cycle actually reported to ACCESS.
        state_payload["last_successful_usage_export_at"] = datetime.now(UTC).isoformat()
    else:
        status_message = (
            f"GPU usage collected; submission is disabled ({disabled_reason}) "
            "so nothing was submitted"
        )
    _update_worker_status(
        is_active=True,
        current_state="idle",
        status_message=status_message,
        state_payload=state_payload,
        mark_success=True,
    )
    _evaluate_alerts()
    return result


def run_worker(poll_interval: int | None = None) -> None:
    """Run the GPU usage export loop indefinitely."""
    interval_seconds = poll_interval or (settings.amie_usage_interval_minutes * 60)
    service = GpuAccountingService()

    disabled_reason = service.submission_disabled_reason()
    if disabled_reason is not None:
        logger.warning(
            "GPU usage submission is disabled (%s); usage will be collected but not submitted.",
            disabled_reason,
        )

    logger.info(
        "GPU usage worker started (site=%s accounting_api=%s usage_url=%s resource=%s interval=%ss)",
        settings.amie_site_name,
        settings.nrp_accounting_api_url,
        settings.amie_usage_url,
        settings.amie_gpu_resource_name,
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
                run_once(service)
            except Exception as exc:  # noqa: BLE001
                _update_worker_status(
                    is_active=True,
                    current_state="error",
                    status_message=str(exc),
                    mark_error=True,
                )
                logger.exception("GPU usage worker error")

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
