"""Cross-service audit service."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.kubernetes.service import KubernetesProvisioningService


class AuditService:
    """Runs consistency checks across DB and integrated services."""

    def __init__(
        self,
        kubernetes_service: KubernetesProvisioningService | None = None,
    ) -> None:
        self.kubernetes_service = kubernetes_service or KubernetesProvisioningService()

    def _desired_project_member_identifiers(
        self,
        db: Session,
        *,
        project: Project,
    ) -> tuple[set[str], list[dict[str, str | None]]]:
        rows = (
            db.query(ProjectUser, User)
            .join(User, User.id == ProjectUser.user_id)
            .filter(
                ProjectUser.project_id == project.id,
                ProjectUser.is_active.is_(True),
            )
            .all()
        )
        desired: set[str] = set()
        missing: list[dict[str, str | None]] = []
        for project_user, user in rows:
            identifier = self.kubernetes_service.membership_identifier(
                user=user,
                project_user=project_user,
            )
            if identifier:
                desired.add(identifier)
            else:
                missing.append(
                    {
                        "project_user_id": str(project_user.id),
                        "user_id": str(user.id),
                        "email": user.email,
                    }
                )
        return desired, missing

    def _portal_namespace_membership_check(self, db: Session) -> dict:
        """Compare active DB memberships with portal namespace memberships."""
        active_projects = db.query(Project).filter(Project.is_active.is_(True)).all()

        missing_namespace_mapping = [
            {
                "project_id": str(project.id),
                "site_project_id": project.site_project_id,
            }
            for project in active_projects
            if not project.kubernetes_namespace
        ]
        projects_with_namespace = [p for p in active_projects if p.kubernetes_namespace]

        list_result = self.kubernetes_service.list_all_namespaces()
        portal_namespace_set = set(list_result.get("namespaces", [])) if list_result.get("ok") else set()
        portal_only_namespaces = []
        if list_result.get("ok"):
            db_namespaces = {
                str(project.kubernetes_namespace)
                for project in projects_with_namespace
                if project.kubernetes_namespace
            }
            portal_only_namespaces = sorted(portal_namespace_set - db_namespaces)

        compared_projects = 0
        unavailable_projects = 0
        missing_portal_namespaces: list[dict] = []
        mismatches: list[dict] = []
        missing_identifiers_by_project: list[dict] = []

        for project in projects_with_namespace:
            namespace = str(project.kubernetes_namespace)
            if list_result.get("ok") and namespace not in portal_namespace_set:
                missing_portal_namespaces.append(
                    {
                        "project_id": str(project.id),
                        "site_project_id": project.site_project_id,
                        "namespace": namespace,
                    }
                )
                continue

            users_result = self.kubernetes_service.get_namespace_users(namespace=namespace)
            if not users_result.get("ok"):
                unavailable_projects += 1
                continue

            compared_projects += 1
            desired_members, missing_identifiers = self._desired_project_member_identifiers(
                db,
                project=project,
            )
            if missing_identifiers:
                missing_identifiers_by_project.append(
                    {
                        "project_id": str(project.id),
                        "site_project_id": project.site_project_id,
                        "namespace": namespace,
                        "missing_identifiers": missing_identifiers,
                    }
                )
            actual_members = set(users_result.get("user_ids", []))
            only_in_db = sorted(desired_members - actual_members)
            only_in_portal = sorted(actual_members - desired_members)
            if only_in_db or only_in_portal:
                mismatches.append(
                    {
                        "project_id": str(project.id),
                        "site_project_id": project.site_project_id,
                        "namespace": namespace,
                        "db_member_count": len(desired_members),
                        "portal_member_count": len(actual_members),
                        "only_in_db": only_in_db,
                        "only_in_portal": only_in_portal,
                        "missing_identifiers": missing_identifiers,
                    }
                )

        status = "ok"
        summary = "Portal namespace memberships are in sync with database"
        if not list_result.get("ok"):
            status = "stub"
            summary = (
                "Portal namespace list API unavailable; namespace membership sync check is stubbed"
            )
        elif missing_namespace_mapping:
            status = "warn"
            summary = (
                f"{len(missing_namespace_mapping)} active project(s) are missing namespace mapping"
            )
        elif missing_portal_namespaces:
            status = "warn"
            summary = (
                f"{len(missing_portal_namespaces)} project namespace(s) are missing from portal"
            )
        elif missing_identifiers_by_project:
            status = "warn"
            summary = (
                f"{len(missing_identifiers_by_project)} project(s) have members without "
                "stored portal usernames"
            )
        elif mismatches:
            status = "warn"
            summary = (
                f"Found {len(mismatches)} project namespace(s) with portal membership drift"
            )
        elif unavailable_projects:
            status = "warn"
            summary = (
                f"Compared {compared_projects} projects; "
                f"{unavailable_projects} project(s) unavailable from portal"
            )

        return {
            "service": "portal_namespace_membership_sync",
            "status": status,
            "summary": summary,
            "details": {
                "active_projects": len(active_projects),
                "projects_with_namespace": len(projects_with_namespace),
                "compared_projects": compared_projects,
                "unavailable_projects": unavailable_projects,
                "missing_namespace_mapping_count": len(missing_namespace_mapping),
                "missing_namespace_mapping": missing_namespace_mapping,
                "missing_portal_namespaces_count": len(missing_portal_namespaces),
                "missing_portal_namespaces": missing_portal_namespaces,
                "mismatch_projects": len(mismatches),
                "mismatches": mismatches,
                "portal_only_namespaces": portal_only_namespaces,
                "missing_identifier_projects_count": len(missing_identifiers_by_project),
                "missing_identifier_projects": missing_identifiers_by_project,
            },
        }

    def sync_portal_namespace_memberships(
        self,
        db: Session,
        *,
        apply_changes: bool = False,
    ) -> dict:
        """Audit and optionally reconcile portal namespace + membership drift."""
        check = self._portal_namespace_membership_check(db)
        details = check.get("details", {})
        actions: list[dict] = []

        if not apply_changes:
            return {
                "mode": "dry_run",
                "status": check.get("status", "stub"),
                "summary": check.get("summary", ""),
                "details": details,
                "actions": actions,
            }

        active_projects = db.query(Project).filter(Project.is_active.is_(True)).all()

        for project in active_projects:
            namespace = project.kubernetes_namespace or self.kubernetes_service.namespace_for_project(
                project=project
            )
            namespace = str(namespace)

            ensure_result = self.kubernetes_service.ensure_project_namespace(project=project)
            actions.append(
                {
                    "project_id": str(project.id),
                    "namespace": namespace,
                    "action": "ensure_namespace",
                    "result": ensure_result,
                }
            )
            if not ensure_result.get("ok", False):
                continue

            project.kubernetes_namespace = namespace
            project.authentik_group_name = str(
                project.authentik_group_name
                or ensure_result.get("authentik_group_name")
                or namespace
            )

            info_result = self.kubernetes_service.set_project_namespace_info(project=project)
            actions.append(
                {
                    "project_id": str(project.id),
                    "namespace": namespace,
                    "action": "set_namespace_info",
                    "result": info_result,
                }
            )

            users_result = self.kubernetes_service.get_namespace_users(namespace=namespace)
            if not users_result.get("ok", False):
                actions.append(
                    {
                        "project_id": str(project.id),
                        "namespace": namespace,
                        "action": "skip_membership_reconcile",
                        "reason": "namespace_users_unavailable",
                        "result": users_result,
                    }
                )
                continue

            desired_members, missing_identifiers = self._desired_project_member_identifiers(
                db,
                project=project,
            )
            actual_members = set(users_result.get("user_ids", []))

            for identifier in sorted(desired_members - actual_members):
                result = self.kubernetes_service.add_namespace_user(
                    namespace=namespace,
                    user_id=identifier,
                )
                actions.append(
                    {
                        "project_id": str(project.id),
                        "namespace": namespace,
                        "member_identifier": identifier,
                        "action": "ensure_in_portal_namespace",
                        "result": result,
                    }
                )

            if missing_identifiers:
                actions.append(
                    {
                        "project_id": str(project.id),
                        "namespace": namespace,
                        "action": "skip_remove_from_portal_namespace",
                        "reason": "missing_portal_usernames",
                        "missing_identifiers": missing_identifiers,
                    }
                )
            else:
                for identifier in sorted(actual_members - desired_members):
                    result = self.kubernetes_service.remove_namespace_user(
                        namespace=namespace,
                        user_id=identifier,
                    )
                    actions.append(
                        {
                            "project_id": str(project.id),
                            "namespace": namespace,
                            "member_identifier": identifier,
                            "action": "remove_from_portal_namespace",
                            "result": result,
                        }
                    )

        db.commit()
        succeeded = sum(1 for action in actions if action.get("result", {}).get("ok", False))
        failed = len(actions) - succeeded
        return {
            "mode": "apply",
            "status": "ok" if failed == 0 else "warn",
            "summary": (
                f"Applied {len(actions)} portal sync action(s): "
                f"{succeeded} succeeded, {failed} failed"
            ),
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
            .filter(~ProjectUser.account_state.in_(ProjectUser.ALL_ACCOUNT_STATES))
            .count()
        )
        pending_confirmations = (
            db.query(ProjectUser)
            .filter(
                and_(
                    ProjectUser.account_state
                    == ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
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

        checks.append(self._portal_namespace_membership_check(db))

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
