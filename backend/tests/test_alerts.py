"""Tests for alert rendering and project alert payloads."""

from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError, InternalError, OperationalError

from app.models.alert_notification import AlertNotification
from app.models.project import Project
from app.services.alerts import AlertService
from app.services.database_health import (
    database_is_read_only,
    is_database_write_unavailable,
)
from app.services.observability import ObservabilityService
from app.services.project_provisioning import ProjectProvisioningService


def test_build_html_email_renders_project_page_url_as_clickable_link():
    project_url = "https://portal.example.org/projects/1234"

    html = AlertService._build_html_email(
        alert_key="project_provision_required:1234",
        category="project_provisioning",
        severity="warn",
        title="New project request received",
        message="Project ACCESS Project (TG-TEST123) was received and awaits admin provisioning.",
        payload={"project_page": project_url},
    )

    assert "Project Page" in html
    assert f'href="{project_url}"' in html
    assert f">{project_url}</a>" in html


def test_parse_recipients_accepts_comma_separated_email_list():
    recipients = AlertService._parse_recipients(
        "ops@example.org, admin@example.org, , alerts@example.org "
    )

    assert recipients == [
        "ops@example.org",
        "admin@example.org",
        "alerts@example.org",
    ]


def test_send_email_alert_uses_all_configured_recipients():
    with (
        patch(
            "app.services.alerts.settings.alert_email_to",
            "ops@example.org,admin@example.org, alerts@example.org",
        ),
        patch("app.services.alerts.settings.alert_email_from", "alerts@example.org"),
        patch("app.services.alerts.settings.alert_smtp_host", "smtp.example.org"),
        patch("app.services.alerts.settings.alert_smtp_username", ""),
        patch("app.services.alerts.smtplib.SMTP") as mock_smtp,
    ):
        sent = AlertService._send_email_alert(
            alert_key="project_provision_required:1234",
            category="project_provisioning",
            severity="warn",
            title="New project request received",
            message="Project received.",
        )

    smtp = mock_smtp.return_value.__enter__.return_value
    email_message = smtp.send_message.call_args.args[0]
    assert sent is True
    assert email_message["To"] == (
        "ops@example.org, admin@example.org, alerts@example.org"
    )


def test_emit_required_alert_includes_project_page_link(db, make_project):
    project = make_project(
        db,
        lifecycle_state=Project.LIFECYCLE_STATE_PENDING_PROVISIONING,
        provisioning_state=Project.PROVISIONING_STATE_RECEIVED,
        pi_first_name="Pat",
        pi_last_name="Investigator",
        pi_email="pi@example.org",
        pi_organization="Example University",
    )

    service = ProjectProvisioningService()

    with (
        patch(
            "app.services.project_provisioning.settings.frontend_base_url",
            "https://portal.example.org",
        ),
        patch("app.services.project_provisioning.AlertService.send") as mock_send,
    ):
        service.emit_required_alert(db, project=project, reason="new request")

    mock_send.assert_called_once()
    payload = mock_send.call_args.kwargs["payload"]
    assert payload["project_page"] == f"https://portal.example.org/projects/{project.id}"

    db.refresh(project)
    assert project.provisioning_alerted_at is not None


def test_alert_send_can_skip_email_channel(db):
    with (
        patch("app.services.alerts.settings.alert_email_to", "ops@example.org"),
        patch("app.services.alerts.settings.alert_email_from", "alerts@example.org"),
        patch("app.services.alerts.settings.alert_smtp_host", "smtp.example.org"),
        patch("app.services.alerts.AlertService._send_email_alert") as mock_email,
    ):
        result = AlertService.send(
            db,
            alert_key="worker_stale:usage-worker",
            category="worker",
            severity="error",
            title="Worker stale: usage-worker",
            message="Worker heartbeat lag is 600s",
            email_enabled=False,
        )

    mock_email.assert_not_called()
    assert result["sent"] is True
    assert result["channels"] == ["log"]


def test_usage_worker_stale_alert_can_disable_email(db):
    stale_usage_status = {
        "worker_name": "usage-worker",
        "heartbeat_lag_seconds": 3 * 86400,
        "current_state": "error",
        "status_message": "usage export failed",
    }

    with (
        patch(
            "app.services.observability.settings.amie_usage_alert_email_enabled",
            False,
        ),
        patch("app.services.observability.settings.alert_worker_stale_seconds", 300),
        patch(
            "app.services.observability.ObservabilityService.worker_statuses",
            return_value=[stale_usage_status],
        ),
        patch(
            "app.services.observability.ObservabilityService.error_budget_metrics",
            return_value={"parse_failures_total": 0},
        ),
        patch("app.services.observability.AlertService.send") as mock_send,
    ):
        ObservabilityService.evaluate_alerts(db)

    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["alert_key"] == "worker_stale:usage-worker"
    assert mock_send.call_args.kwargs["email_enabled"] is False


# ---------------------------------------------------------------------------
# Throttling when the database cannot accept writes
# ---------------------------------------------------------------------------

class _ReadOnlyTransaction(Exception):
    """Stand-in for psycopg2.errors.ReadOnlySqlTransaction."""

    pgcode = "25006"


def _read_only_error() -> InternalError:
    return InternalError(
        "UPDATE alert_notifications SET ...",
        {},
        _ReadOnlyTransaction("cannot execute UPDATE in a read-only transaction"),
    )


def _send_worker_stale(db):
    return AlertService.send(
        db,
        alert_key="worker_stale:aime-worker",
        category="worker",
        severity="error",
        title="Worker stale: aime-worker",
        message="Worker heartbeat lag is 600s",
    )


def test_alert_throttle_holds_when_database_is_read_only(db):
    with (
        patch("app.services.alerts.settings.alert_min_interval_minutes", 30),
        patch(
            "app.services.alerts.AlertService._send_email_alert", return_value=True
        ) as mock_email,
        patch.object(db, "commit", side_effect=_read_only_error()),
    ):
        first = _send_worker_stale(db)
        second = _send_worker_stale(db)

    assert first["sent"] is True
    assert first["persisted"] is False
    assert second == {"sent": False, "reason": "throttled"}
    mock_email.assert_called_once()


def test_alert_throttle_uses_persisted_last_sent_at(db):
    with (
        patch("app.services.alerts.settings.alert_min_interval_minutes", 30),
        patch(
            "app.services.alerts.AlertService._send_email_alert", return_value=True
        ) as mock_email,
    ):
        first = _send_worker_stale(db)
        # Simulate a worker restart: only the DB row remembers the last send.
        AlertService._process_last_sent.clear()
        second = _send_worker_stale(db)

    assert first["sent"] is True
    assert first["persisted"] is True
    assert second == {"sent": False, "reason": "throttled"}
    mock_email.assert_called_once()


def test_alert_send_persists_throttle_before_dispatch(db):
    seen_last_sent_at = []

    def _record_state(**_kwargs):
        row = (
            db.query(AlertNotification)
            .filter(AlertNotification.alert_key == "worker_stale:aime-worker")
            .one()
        )
        seen_last_sent_at.append(row.last_sent_at)
        return True

    with patch(
        "app.services.alerts.AlertService._send_email_alert", side_effect=_record_state
    ):
        _send_worker_stale(db)

    assert seen_last_sent_at and seen_last_sent_at[0] is not None


def test_alert_send_still_raises_unrelated_commit_errors(db):
    with (
        patch("app.services.alerts.AlertService._send_email_alert") as mock_email,
        patch.object(
            db,
            "commit",
            side_effect=IntegrityError("INSERT ...", {}, Exception("duplicate key")),
        ),
        pytest.raises(IntegrityError),
    ):
        _send_worker_stale(db)

    mock_email.assert_not_called()


def test_alert_resolve_tolerates_read_only_database(db):
    _send_worker_stale(db)

    with patch.object(db, "commit", side_effect=_read_only_error()):
        AlertService.resolve(db, alert_key="worker_stale:aime-worker")


def test_is_database_write_unavailable_classifies_errors():
    assert is_database_write_unavailable(_read_only_error()) is True
    assert is_database_write_unavailable(
        OperationalError("SELECT 1", {}, Exception("server closed the connection"))
    ) is True
    assert is_database_write_unavailable(
        IntegrityError("INSERT ...", {}, Exception("duplicate key"))
    ) is False


# ---------------------------------------------------------------------------
# evaluate_alerts: read-only database and per-worker stale thresholds
# ---------------------------------------------------------------------------

def _evaluate_with_statuses(db, statuses, *, read_only=False):
    with (
        patch(
            "app.services.observability.ObservabilityService.worker_statuses",
            return_value=statuses,
        ),
        patch(
            "app.services.observability.ObservabilityService.error_budget_metrics",
            return_value={"parse_failures_total": 0},
        ),
        patch(
            "app.services.observability.database_is_read_only",
            return_value=read_only,
        ),
        patch("app.services.observability.AlertService.send") as mock_send,
        patch("app.services.observability.AlertService.resolve") as mock_resolve,
    ):
        ObservabilityService.evaluate_alerts(db)
    sent_keys = [c.kwargs["alert_key"] for c in mock_send.call_args_list]
    resolved_keys = [c.kwargs["alert_key"] for c in mock_resolve.call_args_list]
    return sent_keys, resolved_keys


def test_read_only_database_sends_one_database_alert_instead_of_worker_stale(db):
    statuses = [
        {"worker_name": "aime-worker", "heartbeat_lag_seconds": 15878},
        {"worker_name": "usage-worker", "heartbeat_lag_seconds": 500000},
    ]

    sent_keys, resolved_keys = _evaluate_with_statuses(db, statuses, read_only=True)

    assert sent_keys == ["database_read_only"]
    assert "worker_stale:aime-worker" not in resolved_keys


def test_writable_database_resolves_database_read_only_alert(db):
    statuses = [{"worker_name": "aime-worker", "heartbeat_lag_seconds": 10}]

    sent_keys, resolved_keys = _evaluate_with_statuses(db, statuses)

    assert sent_keys == []
    assert "database_read_only" in resolved_keys


def test_usage_worker_is_not_stale_within_its_export_interval(db):
    statuses = [{"worker_name": "usage-worker", "heartbeat_lag_seconds": 3600}]

    with (
        patch("app.services.observability.settings.alert_worker_stale_seconds", 300),
        patch("app.services.observability.settings.amie_usage_interval_minutes", 1440),
    ):
        sent_keys, resolved_keys = _evaluate_with_statuses(db, statuses)

    assert sent_keys == []
    assert "worker_stale:usage-worker" in resolved_keys


def test_usage_worker_is_stale_after_missing_two_export_intervals(db):
    statuses = [
        {"worker_name": "usage-worker", "heartbeat_lag_seconds": 2 * 86400 + 1}
    ]

    with (
        patch("app.services.observability.settings.alert_worker_stale_seconds", 300),
        patch("app.services.observability.settings.amie_usage_interval_minutes", 1440),
    ):
        sent_keys, _ = _evaluate_with_statuses(db, statuses)

    assert sent_keys == ["worker_stale:usage-worker"]


def test_aime_worker_uses_base_stale_threshold(db):
    statuses = [{"worker_name": "aime-worker", "heartbeat_lag_seconds": 301}]

    with patch("app.services.observability.settings.alert_worker_stale_seconds", 300):
        sent_keys, _ = _evaluate_with_statuses(db, statuses)

    assert sent_keys == ["worker_stale:aime-worker"]


def test_database_is_read_only_is_false_for_sqlite(db):
    assert database_is_read_only(db) is False
