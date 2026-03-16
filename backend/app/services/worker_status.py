"""Worker status persistence service."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.worker_status import WorkerStatus


class WorkerStatusService:
    """Helper methods for writing worker heartbeat/state to the database."""

    @staticmethod
    def update_status(
        db: Session,
        *,
        worker_name: str,
        is_active: bool,
        current_state: str,
        status_message: str | None = None,
        state_payload: dict[str, Any] | None = None,
        mark_success: bool = False,
        mark_error: bool = False,
    ) -> WorkerStatus:
        status = (
            db.query(WorkerStatus)
            .filter(WorkerStatus.worker_name == worker_name)
            .first()
        )
        if status is None:
            status = WorkerStatus(worker_name=worker_name)
            db.add(status)

        status.is_active = is_active
        status.current_state = current_state
        status.status_message = status_message
        status.state_payload = state_payload
        status.last_heartbeat = datetime.now(UTC)
        if mark_success:
            status.last_success_at = status.last_heartbeat
        if mark_error:
            status.last_error_at = status.last_heartbeat
            status.last_error_message = status_message

        db.commit()
        return status
