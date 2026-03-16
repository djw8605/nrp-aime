"""Portal authentication helpers and dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

from app.config import settings


@dataclass(slots=True)
class PortalPrincipal:
    """Authenticated portal principal."""

    email: str | None
    subject: str | None
    name: str | None
    flow: str
    source: str
    is_authenticated: bool = True


def _dev_principal() -> PortalPrincipal:
    return PortalPrincipal(
        email="dev-admin@localhost",
        subject="dev-admin",
        name="Dev Admin",
        flow="admin",
        source="dev_bypass",
        is_authenticated=True,
    )


def _session_principal(payload: dict[str, Any]) -> PortalPrincipal:
    return PortalPrincipal(
        email=str(payload.get("email") or "") or None,
        subject=str(payload.get("subject") or "") or None,
        name=str(payload.get("name") or "") or None,
        flow=str(payload.get("flow") or "admin"),
        source=str(payload.get("source") or "session"),
        is_authenticated=True,
    )


def get_portal_principal_optional(request: Request) -> PortalPrincipal | None:
    """Return authenticated principal when available."""
    if settings.auth_dev_bypass:
        return _dev_principal()

    session_payload = request.session.get("portal_auth")
    if not isinstance(session_payload, dict):
        return None
    return _session_principal(session_payload)


def require_portal_auth(request: Request) -> PortalPrincipal:
    """Dependency that enforces portal authentication."""
    principal = get_portal_principal_optional(request)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return principal
