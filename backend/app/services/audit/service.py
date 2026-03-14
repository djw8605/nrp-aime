"""Cross-service audit service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.authentik.service import AuthentikService


class AuditService:
    """Runs consistency checks across DB and integrated services."""

    def __init__(self, authentik_service: AuthentikService | None = None) -> None:
        self.authentik_service = authentik_service or AuthentikService()

    def run(self, db: Session) -> dict:
        checks: list[dict] = []

        total_projects = db.query(Project).count()
        total_users = db.query(User).count()
        total_accounts = db.query(ProjectUser).count()

        invalid_states = (
            db.query(ProjectUser)
            .filter(~ProjectUser.account_state.in_(ProjectUser.ACCOUNT_STATES))
            .count()
        )
        pending_confirmations = (
            db.query(ProjectUser)
            .filter(
                and_(
                    ProjectUser.account_state
                    == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE,
                    ProjectUser.aime_confirmation_sent_at.is_(None),
                    ProjectUser.is_active.is_(True),
                )
            )
            .count()
        )

        db_status = "ok"
        db_summary = "Database consistency checks passed"
        if invalid_states > 0:
            db_status = "error"
            db_summary = "One or more account rows have invalid lifecycle state values"
        elif pending_confirmations > 0:
            db_status = "warn"
            db_summary = "Some account confirmations to AIME are still pending"

        checks.append(
            {
                "service": "database",
                "status": db_status,
                "summary": db_summary,
                "details": {
                    "total_projects": total_projects,
                    "total_users": total_users,
                    "total_accounts": total_accounts,
                    "invalid_account_states": invalid_states,
                    "pending_aime_confirmations": pending_confirmations,
                },
            }
        )

        authentik = self.authentik_service.health_check()
        checks.append(
            {
                "service": "authentik",
                "status": authentik.get("status", "stub"),
                "summary": authentik.get("message", "Authentik check stub"),
                "details": {},
            }
        )

        active_projects_without_namespace = (
            db.query(Project)
            .filter(Project.is_active.is_(True), Project.kubernetes_namespace.is_(None))
            .count()
        )
        k8s_status = "stub"
        k8s_summary = "Kubernetes API checks are stubbed; namespace sanity check only"
        if active_projects_without_namespace > 0:
            k8s_status = "warn"
            k8s_summary = "Some active projects are missing kubernetes namespace mapping"

        checks.append(
            {
                "service": "kubernetes",
                "status": k8s_status,
                "summary": k8s_summary,
                "details": {
                    "active_projects_without_namespace": active_projects_without_namespace,
                },
            }
        )

        # Placeholder hook for future service integrations.
        checks.append(
            {
                "service": "other_services",
                "status": "stub",
                "summary": "Additional service audits are not implemented yet",
                "details": {},
            }
        )

        status_order = {"ok": 0, "stub": 1, "warn": 2, "error": 3}
        overall_status = "ok"
        for check in checks:
            if status_order[check["status"]] > status_order[overall_status]:
                overall_status = check["status"]

        return {
            "status": overall_status,
            "checked_at": datetime.now(UTC).isoformat(),
            "checks": checks,
        }
