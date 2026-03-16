"""Cross-service audit service."""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

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

    def _authentik_membership_check(self, db: Session) -> dict:
        """Compare active DB project memberships with Authentik memberships."""
        active_projects = (
            db.query(Project)
            .filter(Project.is_active.is_(True))
            .all()
        )

        compared_projects = 0
        unavailable_projects = 0
        mismatches: list[dict] = []

        for project in active_projects:
            db_memberships_rows = (
                db.query(ProjectUser, User)
                .join(User, User.id == ProjectUser.user_id)
                .filter(
                    ProjectUser.project_id == project.id,
                    ProjectUser.is_active.is_(True),
                )
                .all()
            )
            desired_members = {
                identifier
                for pu, user in db_memberships_rows
                for identifier in [
                    self.authentik_service.membership_identifier(
                        user=user,
                        project_user=pu,
                    )
                ]
                if identifier
            }

            authentik_members = self.authentik_service.list_project_member_identifiers(
                project=project
            )
            if authentik_members is None:
                unavailable_projects += 1
                continue

            compared_projects += 1
            only_in_db = sorted(desired_members - authentik_members)
            only_in_authentik = sorted(authentik_members - desired_members)
            if only_in_db or only_in_authentik:
                mismatches.append(
                    {
                        "project_id": str(project.id),
                        "site_project_id": project.site_project_id,
                        "db_member_count": len(desired_members),
                        "authentik_member_count": len(authentik_members),
                        "only_in_db": only_in_db,
                        "only_in_authentik": only_in_authentik,
                    }
                )

        status = "ok"
        summary = "Authentik memberships are in sync with database"
        if unavailable_projects and unavailable_projects == len(active_projects):
            status = "stub"
            summary = "Authentik membership list API is not available; sync check is stubbed"
        elif mismatches:
            status = "warn"
            summary = (
                f"Found {len(mismatches)} project(s) with Authentik membership drift"
            )
        elif unavailable_projects:
            status = "warn"
            summary = (
                f"Compared {compared_projects} projects; "
                f"{unavailable_projects} project(s) unavailable from Authentik"
            )

        return {
            "service": "authentik_membership_sync",
            "status": status,
            "summary": summary,
            "details": {
                "active_projects": len(active_projects),
                "compared_projects": compared_projects,
                "unavailable_projects": unavailable_projects,
                "mismatch_projects": len(mismatches),
                "mismatches": mismatches,
            },
        }

    def sync_authentik_memberships(
        self,
        db: Session,
        *,
        apply_changes: bool = False,
    ) -> dict:
        """Audit and optionally reconcile Authentik membership drift."""
        check = self._authentik_membership_check(db)
        details = check.get("details", {})
        mismatches = details.get("mismatches", [])
        actions: list[dict] = []

        if not apply_changes:
            return {
                "mode": "dry_run",
                "status": check.get("status", "stub"),
                "summary": check.get("summary", ""),
                "details": details,
                "actions": actions,
            }

        for mismatch in mismatches:
            project_id = mismatch.get("project_id")
            if not project_id:
                continue
            try:
                project_uuid = uuid.UUID(str(project_id))
            except ValueError:
                actions.append(
                    {
                        "project_id": project_id,
                        "action": "skip",
                        "reason": "invalid_project_id",
                    }
                )
                continue
            project = db.query(Project).filter(Project.id == project_uuid).first()
            if project is None:
                actions.append(
                    {
                        "project_id": project_id,
                        "action": "skip",
                        "reason": "project_not_found",
                    }
                )
                continue

            for identifier in mismatch.get("only_in_db", []):
                result = self.authentik_service.ensure_project_member_identifier(
                    project=project,
                    member_identifier=identifier,
                )
                actions.append(
                    {
                        "project_id": project_id,
                        "member_identifier": identifier,
                        "action": "ensure_in_authentik",
                        "result": result,
                    }
                )

            for identifier in mismatch.get("only_in_authentik", []):
                result = self.authentik_service.remove_project_member_identifier(
                    project=project,
                    member_identifier=identifier,
                )
                actions.append(
                    {
                        "project_id": project_id,
                        "member_identifier": identifier,
                        "action": "remove_from_authentik",
                        "result": result,
                    }
                )

        synced = sum(
            1
            for item in actions
            if item.get("result", {}).get("ok", False)
        )
        failed = len(actions) - synced
        return {
            "mode": "apply",
            "status": "ok" if failed == 0 else "warn",
            "summary": f"Applied {len(actions)} sync action(s): {synced} succeeded, {failed} failed",
            "details": details,
            "actions": actions,
        }

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
        checks.append(self._authentik_membership_check(db))

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
