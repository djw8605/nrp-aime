"""Authentik integration service.

Current implementation centralizes all Authentik interactions and keeps
real API wiring isolated from business logic.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from typing import Any
from urllib.parse import urlencode

from app.config import settings
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User

logger = logging.getLogger(__name__)


class AuthentikService:
    """Wrapper around Authentik interactions."""

    # Dev-only, process-local stub membership store:
    # {project_key: {"member_identifier", ...}}
    _stub_memberships: dict[str, set[str]] = {}

    # Dev-only group-based memberships for invite flow:
    # {group_name: {"member_identifier", ...}}
    _stub_group_memberships: dict[str, set[str]] = {}
    _stub_project_groups: set[str] = set()

    @staticmethod
    def _project_key(project: Project) -> str:
        return (
            project.site_project_id
            or project.grant_number
            or project.aime_allocation_id
            or str(project.id)
        )

    @staticmethod
    def membership_identifier(
        *,
        user: User,
        project_user: ProjectUser | None = None,
    ) -> str | None:
        """Best identifier for Authentik membership operations."""
        if project_user is not None and project_user.remote_site_login:
            return project_user.remote_site_login
        if user.remote_site_login:
            return user.remote_site_login
        if user.person_id:
            return user.person_id
        if user.email:
            return user.email
        return None

    def create_login_redirect(
        self,
        *,
        callback_url: str,
        state: str,
        flow: str = "invite",
    ) -> str:
        """Build Authentik login redirect URL.

        TODO(prod): switch to OIDC session flow with nonce + PKCE and verify
        callback tokens cryptographically.
        """
        if flow == "admin":
            authorize_url = settings.auth_admin_authorize_url
            client_id = settings.auth_admin_client_id
            scope = settings.auth_admin_scope
            stub_email = settings.auth_admin_stub_login_email
        else:
            authorize_url = settings.authentik_authorize_url
            client_id = settings.authentik_client_id
            scope = settings.authentik_scope
            stub_email = settings.authentik_stub_login_email

        if authorize_url and client_id:
            query = {
                "client_id": client_id,
                "response_type": "code",
                "scope": scope,
                "redirect_uri": callback_url,
                "state": state,
            }
            return f"{authorize_url}?{urlencode(query)}"

        params = {"state": state}
        if stub_email:
            params["email"] = stub_email
        return f"{callback_url}?{urlencode(params)}"

    def validate_callback(
        self,
        *,
        code: str | None,
        state: str,
        request_params: dict[str, Any] | None = None,
        flow: str = "invite",
    ) -> dict[str, Any]:
        """Validate callback parameters and return authenticated identity.

        TODO(prod): exchange OIDC auth code for tokens and validate signature,
        issuer, audience, expiration, and nonce.
        """
        _ = state
        params = request_params or {}
        if params.get("error"):
            raise ValueError(f"Authentik error: {params.get('error')}")

        if flow == "admin":
            configured = bool(
                settings.auth_admin_authorize_url and settings.auth_admin_client_id
            )
            stub_email = settings.auth_admin_stub_login_email
        else:
            configured = bool(
                settings.authentik_authorize_url and settings.authentik_client_id
            )
            stub_email = settings.authentik_stub_login_email
        if configured and not code:
            raise ValueError("Missing authorization code")

        email = (
            params.get("email")
            or stub_email
            or params.get("upn")
            or params.get("preferred_username")
        )
        if not email:
            raise ValueError("Unable to resolve authenticated email from callback payload")

        identity = {
            "email": str(email).strip().lower(),
            "subject": params.get("sub") or f"stub:{str(email).strip().lower()}",
            "name": params.get("name"),
        }
        logger.debug("Resolved Authentik callback identity=%s", identity)
        return identity

    def map_project_to_group(
        self,
        *,
        project_id: str,
        project: Project | None = None,
        group_identifier: str | None = None,
    ) -> str:
        """Map a project into an Authentik group identifier."""
        if group_identifier:
            return group_identifier

        if project is not None and project.site_project_id:
            return f"nrp-project-{project.site_project_id}"
        if project is not None and project.grant_number:
            return f"nrp-grant-{project.grant_number}"
        return f"nrp-project-{project_id}"

    def ensure_project_group(self, *, project: Project) -> dict[str, Any]:
        """Ensure Authentik group exists for a project (stub)."""
        group_name = self.map_project_to_group(
            project_id=str(project.id),
            project=project,
        )
        if settings.authentik_base_url and settings.authentik_api_token:
            # TODO(prod): call Authentik API to create/get group.
            logger.info(
                "STUB(authentik api): ensure project group project=%s group=%s",
                self._project_key(project),
                group_name,
            )
            return {
                "ok": True,
                "status": "stub_api",
                "group_name": group_name,
            }

        self._stub_project_groups.add(group_name)
        self._stub_group_memberships.setdefault(group_name, set())
        logger.info(
            "STUB(authentik): ensured project group project=%s group=%s",
            self._project_key(project),
            group_name,
        )
        return {
            "ok": True,
            "status": "stub",
            "group_name": group_name,
        }

    def ensure_user_in_group(
        self,
        *,
        user_identity: dict[str, Any],
        group_name: str,
    ) -> dict[str, Any]:
        """Ensure a callback identity belongs to a given Authentik group."""
        identifier = user_identity.get("email") or user_identity.get("subject")
        if not identifier:
            return {"ok": False, "status": "skipped", "reason": "missing_identifier"}

        if settings.authentik_base_url and settings.authentik_api_token:
            # Future: call Authentik API to ensure group membership.
            logger.info(
                "STUB(authentik api): ensure group membership group=%s user=%s",
                group_name,
                identifier,
            )
            return {
                "ok": True,
                "status": "stub_api",
                "group_name": group_name,
                "user": identifier,
            }

        members = self._stub_group_memberships.setdefault(group_name, set())
        members.add(str(identifier))
        logger.info(
            "STUB(authentik): ensured group membership group=%s user=%s",
            group_name,
            identifier,
        )
        return {
            "ok": True,
            "status": "stub",
            "group_name": group_name,
            "user": str(identifier),
        }

    def list_group_members(self, *, group_name: str) -> set[str] | None:
        """List member identifiers for a group (stub)."""
        if settings.authentik_base_url and settings.authentik_api_token:
            # Future: call Authentik API.
            logger.info("STUB(authentik api): list group members group=%s", group_name)
            return None
        return set(self._stub_group_memberships.get(group_name, set()))

    def remove_user_from_group(
        self,
        *,
        user_identity: dict[str, Any],
        group_name: str,
    ) -> dict[str, Any]:
        """Remove user identity from a group (stub)."""
        identifier = user_identity.get("email") or user_identity.get("subject")
        if not identifier:
            return {"ok": False, "status": "skipped", "reason": "missing_identifier"}

        if settings.authentik_base_url and settings.authentik_api_token:
            # Future: call Authentik API.
            logger.info(
                "STUB(authentik api): remove group membership group=%s user=%s",
                group_name,
                identifier,
            )
            return {
                "ok": True,
                "status": "stub_api",
                "group_name": group_name,
                "user": str(identifier),
            }

        members = self._stub_group_memberships.setdefault(group_name, set())
        members.discard(str(identifier))
        logger.info(
            "STUB(authentik): removed group membership group=%s user=%s",
            group_name,
            identifier,
        )
        return {
            "ok": True,
            "status": "stub",
            "group_name": group_name,
            "user": str(identifier),
        }

    def send_account_creation_email(self, project_id: str, user_email: str) -> None:
        """Send account creation email (legacy stub wrapper)."""
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
        _ = project
        _ = project_user
        if settings.authentik_stub_auto_account_made:
            return bool(
                project_user.remote_site_login
                or user.remote_site_login
                or user.person_id
                or user.email
            )
        return False

    def ensure_user_in_project(
        self,
        *,
        user: User,
        project: Project,
        project_user: ProjectUser | None = None,
    ) -> dict[str, Any]:
        """Ensure user has project membership in Authentik."""
        identifier = self.membership_identifier(user=user, project_user=project_user)
        if not identifier:
            return {"ok": False, "status": "skipped", "reason": "missing_identifier"}
        return self.ensure_project_member_identifier(
            project=project,
            member_identifier=identifier,
        )

    def ensure_project_member_identifier(
        self,
        *,
        project: Project,
        member_identifier: str,
    ) -> dict[str, Any]:
        """Ensure an identifier has project membership in Authentik."""
        if not member_identifier:
            return {"ok": False, "status": "skipped", "reason": "missing_identifier"}

        project_key = self._project_key(project)
        if settings.authentik_base_url and settings.authentik_api_token:
            # Future: call Authentik API to ensure group membership.
            logger.info(
                "STUB(authentik api): ensure membership project=%s user=%s",
                project_key,
                member_identifier,
            )
            return {"ok": True, "status": "stub_api", "project_key": project_key}

        members = self._stub_memberships.setdefault(project_key, set())
        members.add(member_identifier)
        logger.info(
            "STUB(authentik): ensured membership project=%s user=%s",
            project_key,
            member_identifier,
        )
        return {
            "ok": True,
            "status": "stub",
            "project_key": project_key,
            "user": member_identifier,
        }

    def remove_user_from_project(
        self,
        *,
        user: User,
        project: Project,
        project_user: ProjectUser | None = None,
    ) -> dict[str, Any]:
        """Remove user project membership in Authentik."""
        identifier = self.membership_identifier(user=user, project_user=project_user)
        if not identifier:
            return {"ok": False, "status": "skipped", "reason": "missing_identifier"}
        return self.remove_project_member_identifier(
            project=project,
            member_identifier=identifier,
        )

    def remove_project_member_identifier(
        self,
        *,
        project: Project,
        member_identifier: str,
    ) -> dict[str, Any]:
        """Remove an identifier from project membership in Authentik."""
        if not member_identifier:
            return {"ok": False, "status": "skipped", "reason": "missing_identifier"}

        project_key = self._project_key(project)
        if settings.authentik_base_url and settings.authentik_api_token:
            # Future: call Authentik API to remove group membership.
            logger.info(
                "STUB(authentik api): remove membership project=%s user=%s",
                project_key,
                member_identifier,
            )
            return {"ok": True, "status": "stub_api", "project_key": project_key}

        members = self._stub_memberships.setdefault(project_key, set())
        members.discard(member_identifier)
        logger.info(
            "STUB(authentik): removed membership project=%s user=%s",
            project_key,
            member_identifier,
        )
        return {
            "ok": True,
            "status": "stub",
            "project_key": project_key,
            "user": member_identifier,
        }

    def list_project_member_identifiers(self, *, project: Project) -> set[str] | None:
        """Return Authentik members for a project, or None if unavailable."""
        project_key = self._project_key(project)
        if settings.authentik_base_url and settings.authentik_api_token:
            # Future: call Authentik API and return actual identifiers.
            logger.info(
                "STUB(authentik api): list members project=%s",
                project_key,
            )
            return None
        return set(self._stub_memberships.get(project_key, set()))

    def health_check(self) -> dict[str, str]:
        """Return service health/info for audit runs."""
        configured = bool(settings.authentik_base_url and settings.authentik_api_token)
        if configured:
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
