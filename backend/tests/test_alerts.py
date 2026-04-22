"""Tests for alert rendering and project alert payloads."""

from unittest.mock import patch

from app.models.project import Project
from app.services.alerts import AlertService
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
