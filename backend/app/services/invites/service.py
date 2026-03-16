"""Project invite service logic for special-link onboarding flow."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.project import Project
from app.models.project_invite import ProjectInvite
from app.models.project_invite_event import ProjectInviteEvent
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.account_lifecycle import AccountLifecycleService
from app.services.authentik.service import AuthentikService
from app.services.email.service import EmailService
from app.services.kubernetes.service import KubernetesProvisioningService
from app.utils.security import (
    generate_secure_token,
    hash_invite_token,
    mask_email,
    sign_state,
    verify_state,
)

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,200}$")


class InviteFlowError(Exception):
    """Domain error for invite flow operations."""

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(slots=True)
class InviteCreationResult:
    """Created invite details including raw URL for immediate use."""

    invite: ProjectInvite
    invite_url: str
    raw_token: str


class InviteService:
    """Business logic for invite creation, preview, and callback finalization."""

    def __init__(
        self,
        *,
        authentik_service: AuthentikService | None = None,
        email_service: EmailService | None = None,
        kubernetes_service: KubernetesProvisioningService | None = None,
    ) -> None:
        self.authentik_service = authentik_service or AuthentikService()
        self.email_service = email_service or EmailService()
        self.kubernetes_service = kubernetes_service or KubernetesProvisioningService()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def _is_valid_token_format(token: str) -> bool:
        return bool(_TOKEN_PATTERN.fullmatch((token or "").strip()))

    def _frontend_url(self, path: str, *, query: dict[str, Any] | None = None) -> str:
        base = settings.frontend_base_url.rstrip("/")
        route = path if path.startswith("/") else f"/{path}"
        if not query:
            return f"{base}{route}"
        safe_query = {k: v for k, v in query.items() if v is not None}
        return f"{base}{route}?{urlencode(safe_query)}"

    def _backend_callback_url(self) -> str:
        base = settings.backend_base_url.rstrip("/")
        path = str(settings.authentik_redirect_path or "").strip()
        if "://" in path:
            return path
        if not path:
            path = "/api/v1/invites/callback"
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{base}{path}"

    def _record_event(
        self,
        db: Session,
        *,
        event_type: str,
        event_status: str = "info",
        invite: ProjectInvite | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ProjectInviteEvent:
        event = ProjectInviteEvent(
            invite_id=invite.id if invite else None,
            event_type=event_type,
            event_status=event_status,
            message=message,
            event_payload=payload or {},
        )
        db.add(event)
        db.flush()
        return event

    def record_unbound_failure(
        self,
        db: Session,
        *,
        event_type: str,
        code: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Record invite-flow failure not tied to a specific invite row."""
        self._record_event(
            db,
            event_type=event_type,
            event_status="error",
            invite=None,
            message=message,
            payload={"code": code, **(payload or {})},
        )
        db.commit()

    def _get_project(self, db: Session, project_id: uuid.UUID) -> Project:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is None:
            raise InviteFlowError(code="project_not_found", message="Project not found")
        return project

    def _get_user(self, db: Session, user_id: uuid.UUID) -> User:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise InviteFlowError(code="user_not_found", message="User not found")
        return user

    def _active_memberships_for_user(self, db: Session, *, user_id: uuid.UUID) -> list[ProjectUser]:
        return (
            db.query(ProjectUser)
            .options(joinedload(ProjectUser.project))
            .filter(
                ProjectUser.user_id == user_id,
                ProjectUser.is_active.is_(True),
            )
            .order_by(ProjectUser.created_at.asc())
            .all()
        )

    @staticmethod
    def _username_for_success(*, user: User, project_users: list[ProjectUser]) -> str:
        for membership in project_users:
            if membership.remote_site_login:
                return membership.remote_site_login
        if user.remote_site_login:
            return user.remote_site_login
        if user.email and "@" in user.email:
            return user.email.split("@", 1)[0]
        if user.person_id:
            return user.person_id
        return str(user.id)

    def _expire_if_needed(self, db: Session, invite: ProjectInvite) -> bool:
        if invite.status != ProjectInvite.STATUS_PENDING:
            return invite.status == ProjectInvite.STATUS_EXPIRED
        if invite.expires_at <= self._now():
            invite.status = ProjectInvite.STATUS_EXPIRED
            self._record_event(
                db,
                event_type="invite_expired",
                event_status="warn",
                invite=invite,
                message="Invite expired before completion",
                payload={
                    "invite_id": str(invite.id),
                    "project_id": str(invite.project_id) if invite.project_id else None,
                    "user_id": str(invite.user_id) if invite.user_id else None,
                },
            )
            return True
        return False

    def _lookup_invite_by_token(
        self,
        db: Session,
        *,
        token: str,
        include_project: bool = False,
        include_user: bool = False,
    ) -> ProjectInvite:
        normalized_token = (token or "").strip()
        if not self._is_valid_token_format(normalized_token):
            raise InviteFlowError(code="invalid_invite", message="Invalid invitation link")

        token_hash = hash_invite_token(normalized_token)
        query = db.query(ProjectInvite)
        if include_project:
            query = query.options(joinedload(ProjectInvite.project))
        if include_user:
            query = query.options(joinedload(ProjectInvite.user))
        invite = query.filter(ProjectInvite.token_hash == token_hash).first()
        if invite is None:
            self._record_event(
                db,
                event_type="invite_lookup_failed",
                event_status="warn",
                message="Invite token was not found",
                payload={"token_hash_prefix": token_hash[:12]},
            )
            db.commit()
            raise InviteFlowError(code="invalid_invite", message="Invalid invitation link")

        if self._expire_if_needed(db, invite):
            db.commit()
        return invite

    def create_invite(
        self,
        db: Session,
        *,
        project_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        email: str,
        expires_in_hours: int | None = None,
        invited_by: str | None = None,
        authentik_group_name: str | None = None,
        redirect_path: str | None = None,
        metadata: dict[str, Any] | None = None,
        send_email: bool = True,
    ) -> InviteCreationResult:
        """Create one invite with secure token and audit event.

        Supports project-scoped and person-scoped invites.
        """
        project: Project | None = None
        user: User | None = None
        if project_id is not None:
            project = self._get_project(db, project_id)
        if user_id is not None:
            user = self._get_user(db, user_id)
        if project is None and user is None:
            raise InviteFlowError(
                code="invite_scope_required",
                message="Invite must target a user and/or project",
            )

        normalized_email = self._normalize_email(email)
        if user is not None and user.email:
            user_email = self._normalize_email(user.email)
            if user_email != normalized_email:
                raise InviteFlowError(
                    code="invite_email_mismatch",
                    message="Invite email does not match the selected user account",
                )

        ttl_hours = expires_in_hours or settings.invite_token_ttl_hours

        raw_token = generate_secure_token()
        token_hash = hash_invite_token(raw_token)
        expires_at = self._now() + timedelta(hours=max(1, int(ttl_hours)))
        group_name = authentik_group_name
        if group_name is None and project is not None:
            group_name = project.authentik_group_name or project.kubernetes_namespace
            if group_name is None:
                group_name = self.authentik_service.map_project_to_group(
                    project_id=str(project.id),
                    project=project,
                )

        user_project_names: list[str] = []
        if user is not None:
            user_project_names = sorted(
                {
                    membership.project.name
                    for membership in self._active_memberships_for_user(db, user_id=user.id)
                    if membership.project is not None and membership.project.name
                }
            )

        invite = ProjectInvite(
            project_id=project.id if project is not None else None,
            user_id=user.id if user is not None else None,
            email=normalized_email,
            token_hash=token_hash,
            status=ProjectInvite.STATUS_PENDING,
            expires_at=expires_at,
            invited_by=invited_by,
            authentik_group_name=group_name,
            redirect_path=redirect_path,
            invite_metadata=metadata or {},
        )
        db.add(invite)
        db.flush()

        invite_url = self._frontend_url("/invite/accept", query={"token": raw_token})
        self._record_event(
            db,
            event_type="invite_created",
            invite=invite,
            message="Invite created",
            payload={
                "project_id": str(project.id) if project is not None else None,
                "user_id": str(user.id) if user is not None else None,
                "email": normalized_email,
                "authentik_group_name": group_name,
                "project_names": user_project_names,
            },
        )

        if send_email:
            self.email_service.send_project_invite_email(
                to_email=normalized_email,
                project_name=project.name if project is not None else None,
                project_names=user_project_names,
                invite_url=invite_url,
                expires_at=expires_at,
            )
            self._record_event(
                db,
                event_type="invite_email_dispatched",
                invite=invite,
                message="Invite email dispatched",
            )

        db.commit()
        db.refresh(invite)
        return InviteCreationResult(invite=invite, invite_url=invite_url, raw_token=raw_token)

    def preview_invite(self, db: Session, *, token: str) -> dict[str, Any]:
        """Return safe preview data for invite landing page."""
        try:
            invite = self._lookup_invite_by_token(
                db,
                token=token,
                include_project=True,
                include_user=True,
            )
        except InviteFlowError:
            return {
                "valid": False,
                "status": "invalid",
                "message": "Invalid invitation link",
            }

        if invite.status != ProjectInvite.STATUS_PENDING:
            message = {
                ProjectInvite.STATUS_USED: "This invitation link has already been used",
                ProjectInvite.STATUS_EXPIRED: "This invitation link has expired",
                ProjectInvite.STATUS_REVOKED: "This invitation link has been revoked",
            }.get(invite.status, "Invitation link is not available")
            return {
                "valid": False,
                "status": invite.status,
                "message": message,
            }

        project_names: list[str] = []
        if invite.user_id is not None:
            project_names = sorted(
                {
                    membership.project.name
                    for membership in self._active_memberships_for_user(
                        db, user_id=invite.user_id
                    )
                    if membership.project is not None and membership.project.name
                }
            )
        elif invite.project and invite.project.name:
            project_names = [invite.project.name]

        user_name = invite.user.name if invite.user is not None else None
        return {
            "valid": True,
            "status": invite.status,
            "user_id": invite.user_id,
            "user_name": user_name,
            "project_id": invite.project_id,
            "project_name": invite.project.name if invite.project else None,
            "project_names": project_names,
            "project_count": len(project_names),
            "invited_email_masked": mask_email(invite.email),
            "expires_at": invite.expires_at,
            "message": "Invitation is valid",
        }

    def begin_accept_flow(self, db: Session, *, token: str) -> str:
        """Validate invite and produce Authentik login redirect URL."""
        invite = self._lookup_invite_by_token(db, token=token, include_project=False)
        if invite.status != ProjectInvite.STATUS_PENDING:
            raise InviteFlowError(
                code=f"invite_{invite.status}",
                message="Invitation is not available",
            )

        state = sign_state({"invite_id": str(invite.id), "token_hash": invite.token_hash})
        callback_url = self._backend_callback_url()
        login_redirect = self.authentik_service.create_login_redirect(
            callback_url=callback_url,
            state=state,
            flow="invite",
        )
        self._record_event(
            db,
            event_type="invite_accept_started",
            invite=invite,
            message="Invite accept flow started",
        )
        db.commit()
        return login_redirect

    def _resolve_state_invite(self, db: Session, *, state: str) -> ProjectInvite:
        try:
            payload = verify_state(
                state,
                max_age_seconds=max(60, settings.invite_state_ttl_minutes * 60),
            )
        except Exception as exc:  # noqa: BLE001
            raise InviteFlowError(code="invalid_state", message=str(exc)) from exc

        invite_id_raw = payload.get("invite_id")
        token_hash = payload.get("token_hash")
        if not invite_id_raw:
            raise InviteFlowError(code="invalid_state", message="Invite state missing")

        try:
            invite_id = uuid.UUID(str(invite_id_raw))
        except ValueError as exc:
            raise InviteFlowError(code="invalid_state", message="Invite state is invalid") from exc

        invite = (
            db.query(ProjectInvite)
            .options(
                joinedload(ProjectInvite.project),
                joinedload(ProjectInvite.user),
            )
            .filter(ProjectInvite.id == invite_id)
            .first()
        )
        if invite is None:
            raise InviteFlowError(code="invalid_invite", message="Invite was not found")

        if token_hash and token_hash != invite.token_hash:
            self._record_event(
                db,
                event_type="invite_state_mismatch",
                event_status="error",
                invite=invite,
                message="State token hash did not match invite",
            )
            raise InviteFlowError(code="invalid_state", message="Invite state mismatch")

        if self._expire_if_needed(db, invite):
            db.commit()
        return invite

    def finalize_callback(
        self,
        db: Session,
        *,
        state: str,
        code: str | None,
        callback_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Complete invite after Authentik callback and bind user to memberships."""
        invite = self._resolve_state_invite(db, state=state)
        if invite.status != ProjectInvite.STATUS_PENDING:
            raise InviteFlowError(
                code=f"invite_{invite.status}",
                message="Invitation is not available",
            )

        identity = self.authentik_service.validate_callback(
            code=code,
            state=state,
            request_params=callback_params,
            flow="invite",
            callback_url=self._backend_callback_url(),
        )
        auth_email = self._normalize_email(str(identity.get("email") or ""))
        auth_username = str(identity.get("username") or "").strip()
        if not auth_email:
            raise InviteFlowError(code="auth_missing_email", message="Authenticated email missing")
        if not auth_username:
            raise InviteFlowError(
                code="auth_missing_username",
                message="Authenticated Authentik username missing",
            )

        invited_email = self._normalize_email(invite.email)
        if settings.invite_require_email_match and auth_email != invited_email:
            self._record_event(
                db,
                event_type="invite_email_mismatch",
                event_status="error",
                invite=invite,
                message="Authenticated email does not match invite email",
                payload={"invite_email": invited_email, "auth_email": auth_email},
            )
            db.commit()
            raise InviteFlowError(
                code="invite_email_mismatch",
                message="Authenticated email does not match the invite email",
            )

        user = invite.user
        if user is None:
            user = (
                db.query(User).filter(User.email == auth_email).first()
                or db.query(User).filter(User.person_id == str(identity.get("subject") or "")).first()
            )
        if user is None:
            user = User(
                email=auth_email,
                name=str(identity.get("name") or auth_email.split("@", 1)[0]),
                person_id=str(identity.get("subject") or "") or None,
                remote_site_login=auth_username,
                is_active=True,
                dn_list=[],
            )
            db.add(user)
            db.flush()
        else:
            user.email = auth_email
            user.remote_site_login = auth_username
            user.is_active = True
            if identity.get("name"):
                user.name = str(identity.get("name"))
            if not user.person_id and identity.get("subject"):
                user.person_id = str(identity.get("subject"))

        memberships = self._active_memberships_for_user(db, user_id=user.id)
        if invite.project_id is not None and all(
            membership.project_id != invite.project_id for membership in memberships
        ):
            project = invite.project or self._get_project(db, invite.project_id)
            membership = ProjectUser(
                project_id=project.id,
                user_id=user.id,
                resource=project.resource_type,
                is_active=True,
            )
            db.add(membership)
            db.flush()
            membership.project = project
            memberships.append(membership)

        applied_group_names: set[str] = set()
        finalized_memberships: list[ProjectUser] = []
        for membership in memberships:
            if membership.project is None:
                continue
            membership.is_active = True
            # Authentik callback username is the authoritative namespace identity.
            membership.remote_site_login = auth_username
            AccountLifecycleService.mark_account_made(membership)

            access_result = self.kubernetes_service.ensure_user_project_access(
                project=membership.project,
                user=user,
                project_user=membership,
            )
            if not access_result.get("ok", False):
                raise InviteFlowError(
                    code="namespace_access_failed",
                    message="Failed to assign namespace/group membership",
                )

            group_name = (
                membership.project.authentik_group_name
                or access_result.get("authentik_group_name")
                or access_result.get("namespace")
            )
            if group_name:
                applied_group_names.add(str(group_name))
            finalized_memberships.append(membership)

        if not finalized_memberships and invite.authentik_group_name:
            applied_group_names.add(invite.authentik_group_name)

        invite.status = ProjectInvite.STATUS_USED
        invite.used_at = self._now()
        invite.user_id = user.id
        if len(applied_group_names) == 1:
            invite.authentik_group_name = next(iter(applied_group_names))
        self._record_event(
            db,
            event_type="invite_used",
            invite=invite,
            message="Invite completed and user bound to account memberships",
            payload={
                "project_id": str(invite.project_id) if invite.project_id else None,
                "user_id": str(user.id),
                "project_user_ids": [str(row.id) for row in finalized_memberships],
                "applied_group_names": sorted(applied_group_names),
            },
        )

        db.commit()
        primary_membership = finalized_memberships[0] if finalized_memberships else None
        username = self._username_for_success(user=user, project_users=finalized_memberships)
        return {
            "invite_id": invite.id,
            "project_id": (
                primary_membership.project_id
                if primary_membership is not None
                else invite.project_id
            ),
            "user_id": user.id,
            "project_user_id": primary_membership.id if primary_membership is not None else None,
            "status": invite.status,
            "redirect_path": invite.redirect_path,
            "username": username,
        }

    def success_redirect_url(self, finalize_result: dict[str, Any]) -> str:
        """Build frontend success redirect URL for callback completion."""
        return self._frontend_url(
            "/invite/success",
            query={
                "invite_id": str(finalize_result.get("invite_id") or ""),
                "project_id": str(finalize_result.get("project_id") or ""),
                "user_id": str(finalize_result.get("user_id") or ""),
                "username": str(finalize_result.get("username") or ""),
            },
        )

    def error_redirect_url(self, *, error_code: str) -> str:
        """Build frontend error redirect URL for callback failures."""
        return self._frontend_url("/invite/error", query={"code": error_code})
