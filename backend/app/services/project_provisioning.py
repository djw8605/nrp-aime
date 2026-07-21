"""Project infrastructure provisioning workflow service."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.project import Project
from app.services.alerts import AlertService
from app.services.kubernetes.service import KubernetesProvisioningService

logger = logging.getLogger(__name__)


class ProjectProvisioningService:
    """Coordinates project namespace/group provisioning and state transitions."""

    def __init__(
        self,
        *,
        kubernetes_service: KubernetesProvisioningService | None = None,
    ) -> None:
        self.kubernetes_service = kubernetes_service or KubernetesProvisioningService()

    @staticmethod
    def _has_pending_pi_account(project: Project) -> bool:
        """Return True if the project has a PI member still awaiting onboarding."""
        from app.models.project_user import ProjectUser

        completed_states = (
            ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
            ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT,
            # Legacy values that also indicate completion.
            ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE,
        )
        for pu in project.project_users:
            # Deactivated memberships (e.g. a transferred-out PI) must not
            # hold the project hostage.
            if not pu.is_active:
                continue
            if str(pu.role or "").strip().lower() == "pi":
                if pu.account_state not in completed_states:
                    return True
        return False

    @classmethod
    def has_pending_pi_account(cls, project: Project) -> bool:
        """Public check for a PI member still awaiting onboarding."""
        return cls._has_pending_pi_account(project)

    @staticmethod
    def _required_alert_key(project: Project) -> str:
        return f"project_provision_required:{project.id}"

    @staticmethod
    def _failed_alert_key(project: Project) -> str:
        return f"project_provision_failed:{project.id}"

    @staticmethod
    def _project_frontend_url(project: Project) -> str:
        base = str(settings.frontend_base_url or "").rstrip("/")
        path = f"/projects/{project.id}"
        return f"{base}{path}" if base else path

    def mark_received(self, db: Session, *, project: Project, reason: str) -> bool:
        """Mark project as received and pending manual provisioning.

        Returns:
            ``True`` when an admin alert should be dispatched.
        """
        now = datetime.now(UTC)
        already_provisioned = (
            project.lifecycle_state in (
                Project.LIFECYCLE_STATE_PROVISIONED,
                # A project awaiting PI onboarding has already had its
                # namespace/group provisioned; it must not re-alert.
                Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT,
                Project.LIFECYCLE_STATE_AIME_NOTIFIED,
                Project.LIFECYCLE_STATE_ACTIVE,
            )
            and project.kubernetes_namespace
            and project.authentik_group_name
        )
        if already_provisioned:
            return False

        # Keep provisioning_state in sync for backwards compatibility.
        if project.provisioning_state != Project.PROVISIONING_STATE_RECEIVED:
            project.provisioning_state = Project.PROVISIONING_STATE_RECEIVED
            project.provisioning_last_error = None
            project.provisioning_started_at = None
            project.provisioning_completed_at = None

        # Advance lifecycle_state if still at initial received.
        if project.lifecycle_state == Project.LIFECYCLE_STATE_RECEIVED:
            project.set_lifecycle_state(Project.LIFECYCLE_STATE_PENDING_PROVISIONING)

        if project.provisioning_requested_at is None:
            project.provisioning_requested_at = now

        _ = reason
        return project.provisioning_alerted_at is None

    @staticmethod
    def mark_waiting_pi_account(project: Project) -> None:
        """Mark project as waiting for PI account creation.

        Called after provisioning completes when the project was created
        via request_project_create and the PI still needs to onboard.
        The namespace must exist before the PI can create their account.
        """
        if project.lifecycle_state == Project.LIFECYCLE_STATE_PROVISIONED:
            project.set_lifecycle_state(Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT)

    @staticmethod
    def mark_pi_account_ready(project: Project) -> None:
        """Advance project past the PI account wait gate.

        Called when the PI completes OAuth.  Moves the project back to
        ``provisioned`` so the reconciler can send ``notify_project_create``.
        """
        if project.lifecycle_state == Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT:
            # Go back to provisioned so the normal notification reconciler
            # picks this project up and sends notify_project_create.
            project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONED)

    def emit_required_alert(self, db: Session, *, project: Project, reason: str) -> None:
        """Send admin alert for newly received project provisioning action."""
        now = datetime.now(UTC)
        if project.provisioning_alerted_at is not None:
            return
        pi_name = " ".join(
            filter(None, [project.pi_first_name, project.pi_last_name])
        ) or None
        AlertService.send(
            db,
            alert_key=self._required_alert_key(project),
            category="project_provisioning",
            severity="warn",
            title="New project request received",
            message=(
                f"Project {project.name} ({project.aime_allocation_id}) was received "
                "and awaits admin provisioning."
            ),
            payload={
                "allocation_id": project.aime_allocation_id,
                "project_name": project.name,
                "project_page": self._project_frontend_url(project),
                "pi_name": pi_name,
                "pi_email": project.pi_email,
                "institution": project.pi_organization,
                "provisioning_state": project.provisioning_state,
            },
        )
        project.provisioning_alerted_at = now
        db.commit()

    def provision_project(
        self,
        db: Session,
        *,
        project: Project,
        requested_by: str = "admin",
    ) -> dict[str, Any]:
        """Provision namespace + group infrastructure for a project."""
        now = datetime.now(UTC)
        project.provisioning_state = Project.PROVISIONING_STATE_PROVISIONING
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONING)
        project.provisioning_started_at = now
        project.provisioning_last_error = None
        if project.provisioning_requested_at is None:
            project.provisioning_requested_at = now
        db.flush()

        namespace_result: dict[str, Any] = {}
        namespace_info_result: dict[str, Any] = {}
        errors: list[str] = []

        try:
            namespace_result = self.kubernetes_service.ensure_project_namespace(project=project)
            if namespace_result.get("ok") and namespace_result.get("namespace"):
                project.kubernetes_namespace = str(namespace_result["namespace"])
                project.authentik_group_name = str(
                    namespace_result.get("authentik_group_name")
                    or namespace_result["namespace"]
                )

                namespace_info_result = self.kubernetes_service.set_project_namespace_info(
                    project=project
                )
                if not namespace_info_result.get("ok", False):
                    errors.append(
                        "portal namespace metadata update failed "
                        f"(result={namespace_info_result})"
                    )
            else:
                errors.append(
                    "portal namespace provisioning failed "
                    f"(result={namespace_result})"
                )

            if errors:
                project.provisioning_state = Project.PROVISIONING_STATE_FAILED
                project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONING_FAILED)
                project.provisioning_last_error = "; ".join(errors)
                project.provisioning_completed_at = None
                AlertService.send(
                    db,
                    alert_key=self._failed_alert_key(project),
                    category="project_provisioning",
                    severity="error",
                    title="Project provisioning failed",
                    message=(
                        f"Provisioning failed for project {project.name} "
                        f"({project.aime_allocation_id})."
                    ),
                    payload={
                        "project_id": str(project.id),
                        "requested_by": requested_by,
                        "errors": errors,
                        "namespace_result": namespace_result,
                        "namespace_info_result": namespace_info_result,
                    },
                )
            else:
                project.provisioning_state = Project.PROVISIONING_STATE_READY
                project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONED)
                project.provisioning_completed_at = datetime.now(UTC)
                project.provisioning_last_error = None
                # Keep provisioning_alerted_at set: the "received" alert has
                # already been raised for this request, and clearing it would
                # let a later re-ingested AMIE packet re-emit a duplicate
                # "New project request received" alert for an already
                # provisioned project.
                AlertService.resolve(db, alert_key=self._required_alert_key(project))
                AlertService.resolve(db, alert_key=self._failed_alert_key(project))

                # If there's a PI that hasn't completed onboarding yet,
                # the project must wait for PI account creation before
                # the AIME notification can be sent.
                if self._has_pending_pi_account(project):
                    self.mark_waiting_pi_account(project)

            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unexpected error provisioning project infrastructure project_id=%s",
                project.id,
            )
            project.provisioning_state = Project.PROVISIONING_STATE_FAILED
            project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONING_FAILED)
            project.provisioning_last_error = str(exc)
            project.provisioning_completed_at = None
            AlertService.send(
                db,
                alert_key=self._failed_alert_key(project),
                category="project_provisioning",
                severity="error",
                title="Project provisioning failed",
                message=(
                    f"Provisioning failed for project {project.name} "
                    f"({project.aime_allocation_id})."
                ),
                payload={
                    "project_id": str(project.id),
                    "requested_by": requested_by,
                    "errors": [str(exc)],
                },
            )
            db.commit()
            errors = [str(exc)]

        return {
            "ok": len(errors) == 0,
            "project_id": str(project.id),
            "provisioning_state": project.provisioning_state,
            "provisioning_last_error": project.provisioning_last_error,
            "kubernetes_namespace": project.kubernetes_namespace,
            "authentik_group_name": project.authentik_group_name,
            "namespace_result": namespace_result,
            "namespace_info_result": namespace_info_result,
            "requested_by": requested_by,
        }
