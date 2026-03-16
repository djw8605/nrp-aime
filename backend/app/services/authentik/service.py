"""Authentik integration service.

Current implementation centralizes all Authentik interactions and keeps
real API wiring isolated from business logic.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime
import json
import logging
from typing import Any
from urllib.parse import urlencode

import httpx

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
    _stub_project_group_attributes: dict[str, dict[str, Any]] = {}
    _oidc_metadata_cache: dict[str, dict[str, Any]] = {}

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

    @staticmethod
    def _clean(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _claim_value(cls, claims: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            raw = claims.get(key)
            if isinstance(raw, str):
                value = raw.strip()
                if value:
                    return value
            elif raw is not None and not isinstance(raw, (dict, list, tuple)):
                return str(raw)
            elif isinstance(raw, (list, tuple)):
                for item in raw:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
        return None

    def _flow_auth_config(self, *, flow: str) -> dict[str, str]:
        if flow == "admin":
            return {
                "authorize_url": self._clean(settings.auth_admin_authorize_url),
                "client_id": self._clean(settings.auth_admin_client_id),
                "client_secret": self._clean(settings.auth_admin_client_secret),
                "scope": self._clean(settings.auth_admin_scope) or "openid profile email",
                "stub_email": self._clean(settings.auth_admin_stub_login_email),
                "oidc_configuration_url": self._clean(
                    settings.auth_admin_oidc_configuration_url
                ),
                "token_url": self._clean(settings.auth_admin_token_url),
                "userinfo_url": self._clean(settings.auth_admin_userinfo_url),
            }

        # Invite flow can use dedicated settings or fall back to admin OIDC settings.
        return {
            "authorize_url": self._clean(settings.authentik_authorize_url),
            "client_id": self._clean(settings.authentik_client_id),
            "client_secret": self._clean(settings.authentik_client_secret)
            or self._clean(settings.auth_admin_client_secret),
            "scope": self._clean(settings.authentik_scope) or "openid profile email",
            "stub_email": self._clean(settings.authentik_stub_login_email),
            "oidc_configuration_url": self._clean(
                settings.authentik_oidc_configuration_url
            )
            or self._clean(settings.auth_admin_oidc_configuration_url),
            "token_url": self._clean(settings.authentik_token_url)
            or self._clean(settings.auth_admin_token_url),
            "userinfo_url": self._clean(settings.authentik_userinfo_url)
            or self._clean(settings.auth_admin_userinfo_url),
        }

    @classmethod
    def _load_oidc_metadata(cls, *, oidc_configuration_url: str) -> dict[str, Any]:
        cached = cls._oidc_metadata_cache.get(oidc_configuration_url)
        if cached is not None:
            return cached

        response = httpx.get(oidc_configuration_url, timeout=10)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("OIDC configuration payload is invalid")
        cls._oidc_metadata_cache[oidc_configuration_url] = payload
        return payload

    def _resolve_oidc_endpoints(
        self,
        *,
        token_url: str,
        userinfo_url: str,
        oidc_configuration_url: str,
    ) -> tuple[str, str]:
        resolved_token_url = token_url
        resolved_userinfo_url = userinfo_url
        if (not resolved_token_url or not resolved_userinfo_url) and oidc_configuration_url:
            try:
                metadata = self._load_oidc_metadata(
                    oidc_configuration_url=oidc_configuration_url
                )
                resolved_token_url = resolved_token_url or self._clean(
                    metadata.get("token_endpoint")
                )
                resolved_userinfo_url = resolved_userinfo_url or self._clean(
                    metadata.get("userinfo_endpoint")
                )
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Failed to resolve OIDC metadata from %s",
                    oidc_configuration_url,
                )
        return resolved_token_url, resolved_userinfo_url

    @staticmethod
    def _decode_unverified_jwt_payload(id_token: str) -> dict[str, Any]:
        parts = id_token.split(".")
        if len(parts) < 2:
            return {}
        payload_segment = parts[1]
        padding = "=" * (-len(payload_segment) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload_segment + padding)
            parsed = json.loads(decoded)
            if isinstance(parsed, dict):
                return parsed
        except Exception:  # noqa: BLE001
            logger.debug("Unable to decode id_token payload for claim fallback")
        return {}

    def _exchange_code_for_claims(
        self,
        *,
        token_url: str,
        userinfo_url: str,
        client_id: str,
        client_secret: str,
        callback_url: str,
        code: str,
    ) -> dict[str, Any]:
        try:
            token_response = httpx.post(
                token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": callback_url,
                },
                headers={"Accept": "application/json"},
                timeout=10,
            )
            token_response.raise_for_status()
            token_payload = token_response.json()
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"OIDC token exchange failed: {exc}") from exc

        if not isinstance(token_payload, dict):
            raise ValueError("OIDC token exchange failed: invalid payload shape")

        claims: dict[str, Any] = {}
        claims.update(token_payload)

        id_token = self._clean(token_payload.get("id_token"))
        if id_token:
            claims.update(self._decode_unverified_jwt_payload(id_token))

        if userinfo_url:
            access_token = self._clean(token_payload.get("access_token"))
            if not access_token:
                raise ValueError("OIDC token exchange failed: access token missing")
            try:
                userinfo_response = httpx.get(
                    userinfo_url,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                    timeout=10,
                )
                userinfo_response.raise_for_status()
                userinfo_payload = userinfo_response.json()
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"OIDC userinfo lookup failed: {exc}") from exc

            if not isinstance(userinfo_payload, dict):
                raise ValueError("OIDC userinfo lookup failed: invalid payload shape")
            claims.update(userinfo_payload)

        return claims

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
        config = self._flow_auth_config(flow=flow)
        authorize_url = config["authorize_url"]
        client_id = config["client_id"]
        scope = config["scope"]
        stub_email = config["stub_email"]

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
        callback_url: str | None = None,
    ) -> dict[str, Any]:
        """Validate callback parameters and return authenticated identity.

        TODO(prod): add full ID-token verification (issuer, audience, nonce).
        """
        _ = state
        params = request_params or {}
        if params.get("error"):
            error_value = str(params.get("error"))
            error_description = str(params.get("error_description") or "").strip()
            if error_description:
                raise ValueError(f"Authentik error: {error_value} ({error_description})")
            raise ValueError(f"Authentik error: {error_value}")

        config = self._flow_auth_config(flow=flow)
        configured = bool(config["authorize_url"] and config["client_id"])
        stub_email = config["stub_email"]

        token_url, userinfo_url = self._resolve_oidc_endpoints(
            token_url=config["token_url"],
            userinfo_url=config["userinfo_url"],
            oidc_configuration_url=config["oidc_configuration_url"],
        )

        if configured and not code:
            raise ValueError("Missing authorization code")

        claims = dict(params)
        has_exchange_config = bool(config["client_id"] and config["client_secret"] and token_url)
        if code and has_exchange_config:
            callback = self._clean(callback_url)
            if not callback:
                raise ValueError("OIDC callback URL is not configured")
            oidc_claims = self._exchange_code_for_claims(
                token_url=token_url,
                userinfo_url=userinfo_url,
                client_id=config["client_id"],
                client_secret=config["client_secret"],
                callback_url=callback,
                code=code,
            )
            claims.update(oidc_claims)
        elif code and configured:
            missing: list[str] = []
            if not config["client_secret"]:
                missing.append("client secret")
            if not token_url:
                missing.append("token endpoint")
            if missing:
                missing_values = ", ".join(missing)
                raise ValueError(f"OIDC code exchange is not configured ({missing_values} missing)")

        username = self._claim_value(
            claims,
            "preferred_username",
            "username",
            "user",
            "login",
            "remote_site_login",
        )
        email = self._claim_value(claims, "email", "upn") or stub_email
        if not email:
            raise ValueError("Unable to resolve authenticated email from callback payload")
        if not username:
            # Compatibility fallback for environments that only expose email.
            username = str(email).strip().lower()
            logger.warning(
                "Authentik callback missing username claim; falling back to email value"
            )

        identity = {
            "email": str(email).strip().lower(),
            "subject": self._claim_value(claims, "sub", "subject")
            or f"stub:{str(email).strip().lower()}",
            "name": self._claim_value(claims, "name"),
            "username": str(username).strip(),
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

    def ensure_project_group(
        self,
        *,
        project: Project,
        attributes: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ensure Authentik group exists for a project (stub)."""
        group_name = self.map_project_to_group(
            project_id=str(project.id),
            project=project,
        )
        group_attributes = dict(attributes or {})
        if "is_k8s_namespace" not in group_attributes:
            group_attributes["is_k8s_namespace"] = True
        if settings.authentik_base_url and settings.authentik_api_token:
            # TODO(prod): call Authentik API to create/get group.
            logger.info(
                "STUB(authentik api): ensure project group project=%s group=%s attributes=%s",
                self._project_key(project),
                group_name,
                group_attributes,
            )
            return {
                "ok": True,
                "status": "stub_api",
                "group_name": group_name,
                "attributes": group_attributes,
            }

        self._stub_project_groups.add(group_name)
        self._stub_project_group_attributes[group_name] = group_attributes
        self._stub_group_memberships.setdefault(group_name, set())
        logger.info(
            "STUB(authentik): ensured project group project=%s group=%s attributes=%s",
            self._project_key(project),
            group_name,
            group_attributes,
        )
        return {
            "ok": True,
            "status": "stub",
            "group_name": group_name,
            "attributes": group_attributes,
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
