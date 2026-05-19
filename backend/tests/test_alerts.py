"""Tests for alert rendering and project alert payloads."""

from unittest.mock import patch

from app.models.project import Project
from app.services.alerts import AlertService
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
        "heartbeat_lag_seconds": 600,
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
