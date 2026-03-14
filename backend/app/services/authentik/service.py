"""Authentik integration service.

Current implementation is intentionally mostly stubbed, but it centralizes
all Authentik interactions so account lifecycle logic can be wired now.
"""

from __future__ import annotations

import logging

from app.config import settings
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User

logger = logging.getLogger(__name__)


class AuthentikService:
    """Wrapper around Authentik interactions."""

    def send_account_creation_email(self, project_id: str, user_email: str) -> None:
        """Send account creation email (stub)."""
        logger.info(
            "STUB(authentik): send_account_creation_email project=%s user=%s",
            project_id,
            user_email,
        )

    def account_exists(
        self,
        *,
        user: User,
        project: Project,
        project_user: ProjectUser,
    ) -> bool:
        """Check whether the account exists in Authentik.

        This is stubbed unless real Authentik integration is configured.
        """
        # Future: call Authentik API when token/base URL is configured.
        if settings.authentik_stub_auto_account_made:
            # Stub heuristic to let end-to-end state transitions run in dev:
            # if we have enough account identity to create confirmation packet,
            # we treat it as existing.
            return bool(
                project_user.remote_site_login
                or user.remote_site_login
                or user.person_id
                or user.email
            )
        return False

    def health_check(self) -> dict:
        """Return service health/info for audit runs."""
        configured = bool(settings.authentik_base_url and settings.authentik_api_token)
        if configured:
            # Future: perform a lightweight real API check.
            return {
                "status": "stub",
                "message": "Authentik configured but active API checks are not implemented yet",
            }
        return {
            "status": "stub",
            "message": "Authentik API not configured; using stub checks",
        }


def send_account_creation_email(project_id: str, user_email: str) -> None:
    """Backwards-compatible function wrapper."""
    AuthentikService().send_account_creation_email(project_id, user_email)
