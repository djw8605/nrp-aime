"""Kubernetes provisioning service (stub)."""

from __future__ import annotations

import logging
import re

from app.models.project_user import ProjectUser
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)

_SAFE_CHARS = re.compile(r"[^a-z0-9-]+")


class KubernetesProvisioningService:
    """Stubbed Kubernetes provisioning operations for project onboarding."""

    @staticmethod
    def _normalize_namespace_fragment(value: str) -> str:
        normalized = _SAFE_CHARS.sub("-", (value or "").strip().lower())
        normalized = normalized.strip("-")
        return normalized[:63] if normalized else "project"

    def namespace_for_project(self, *, project: Project) -> str:
        """Build deterministic namespace name for a project."""
        if project.kubernetes_namespace:
            return project.kubernetes_namespace

        seed = (
            project.site_project_id
            or project.grant_number
            or project.aime_allocation_id
            or str(project.id)
        )
        return f"nrp-{self._normalize_namespace_fragment(seed)}"

    def ensure_project_namespace(self, *, project: Project) -> dict[str, str | bool]:
        """Create namespace for project (stub) and return status."""
        namespace = self.namespace_for_project(project=project)
        logger.info(
            "STUB(kubernetes): ensure namespace project_id=%s namespace=%s",
            project.id,
            namespace,
        )
        return {
            "ok": True,
            "status": "stub",
            "namespace": namespace,
        }

    def ensure_user_project_access(
        self,
        *,
        project: Project,
        user: User,
        project_user: ProjectUser | None = None,
    ) -> dict[str, str | bool]:
        """Ensure user's access binding in project namespace (stub)."""
        namespace = self.namespace_for_project(project=project)
        identity = (
            (project_user.remote_site_login if project_user else None)
            or user.remote_site_login
            or user.person_id
            or user.email
            or str(user.id)
        )
        logger.info(
            "STUB(kubernetes): ensure user access namespace=%s project_id=%s user=%s",
            namespace,
            project.id,
            identity,
        )
        return {
            "ok": True,
            "status": "stub",
            "namespace": namespace,
            "user": str(identity),
        }
