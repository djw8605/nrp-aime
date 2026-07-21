"""Tests for ProjectProvisioningService provisioning + alert de-duplication."""

from datetime import UTC, datetime
from unittest.mock import patch

from app.models.project import Project
from app.models.project_user import ProjectUser
from app.services.project_provisioning import ProjectProvisioningService


class _FakeKubernetesService:
    """Minimal stand-in returning a successful namespace provision."""

    def __init__(self, namespace: str = "nrp-testproj") -> None:
        self.namespace = namespace

    def ensure_project_namespace(self, *, project):  # noqa: ARG002
        return {
            "ok": True,
            "namespace": self.namespace,
            "authentik_group_name": self.namespace,
        }

    def set_project_namespace_info(self, *, project):  # noqa: ARG002
        return {"ok": True}


def _provision(db, project) -> dict:
    service = ProjectProvisioningService(
        kubernetes_service=_FakeKubernetesService()
    )
    return service.provision_project(db, project=project)


class TestProvisioningDoesNotReAlert:
    """A provisioned project must not re-trigger the 'received' admin alert."""

    def test_successful_provision_keeps_alert_guard_set(self, db, make_project):
        """provisioning_alerted_at must not be wiped on success (Defect A)."""
        project = make_project(
            db,
            lifecycle_state=Project.LIFECYCLE_STATE_PENDING_PROVISIONING,
            provisioning_state=Project.PROVISIONING_STATE_RECEIVED,
            provisioning_alerted_at=datetime.now(UTC),
        )

        with patch(
            "app.services.project_provisioning.AlertService.resolve"
        ):
            result = _provision(db, project)

        assert result["ok"] is True
        db.refresh(project)
        # The dedup guard must survive provisioning so no second
        # "New project request received" alert is emitted later.
        assert project.provisioning_alerted_at is not None

    def test_no_realert_after_provision_with_pending_pi(
        self, db, make_project, make_user, make_project_user
    ):
        """After provisioning a PI project (-> waiting_pi_account), a later
        packet must NOT request another 'received' alert (Defect A + B)."""
        project = make_project(
            db,
            lifecycle_state=Project.LIFECYCLE_STATE_PENDING_PROVISIONING,
            provisioning_state=Project.PROVISIONING_STATE_RECEIVED,
            provisioning_alerted_at=datetime.now(UTC),
        )
        pi_user = make_user(db)
        make_project_user(
            db,
            project,
            pi_user,
            role="pi",
            account_state=ProjectUser.ACCOUNT_STATE_RECEIVED,
        )

        service = ProjectProvisioningService(
            kubernetes_service=_FakeKubernetesService()
        )
        with patch(
            "app.services.project_provisioning.AlertService.resolve"
        ):
            service.provision_project(db, project=project)

        db.refresh(project)
        # Provisioning completed but PI has not onboarded yet.
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT
        assert project.kubernetes_namespace

        # A subsequent AMIE packet re-runs mark_received. It must NOT ask for
        # a new alert, because the project is already provisioned.
        needs_alert = service.mark_received(
            db, project=project, reason="packet:request_account_create"
        )
        assert needs_alert is False
