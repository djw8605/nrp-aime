"""Portal authentication API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse

from app.auth import get_portal_principal_optional, require_portal_auth
from app.config import settings
from app.services.authentik.service import AuthentikService
from app.utils.security import sign_state, verify_state

router = APIRouter()


def _frontend_url(path: str, *, query: dict[str, str] | None = None) -> str:
    base = settings.frontend_base_url.rstrip("/")
    route = path if path.startswith("/") else f"/{path}"
    if not query:
        return f"{base}{route}"
    return f"{base}{route}?{urlencode(query)}"


def _backend_admin_callback_url() -> str:
    base = settings.backend_base_url.rstrip("/")
    path = settings.auth_admin_redirect_path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def _safe_next_path(next_path: str | None) -> str:
    value = (next_path or "/").strip()
    if not value.startswith("/"):
        return "/"
    if value.startswith("//"):
        return "/"
    if "://" in value:
        return "/"
    return value or "/"


@router.get("/auth/session")
def get_auth_session(
    principal=Depends(get_portal_principal_optional),
) -> dict:
    """Return current portal auth session."""
    if principal is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "email": principal.email,
        "subject": principal.subject,
        "name": principal.name,
        "flow": principal.flow,
        "source": principal.source,
        "dev_bypass": settings.auth_dev_bypass,
    }


@router.get("/auth/login")
def start_portal_login(
    request: Request,
    next: str = Query(default="/"),
) -> RedirectResponse:
    """Start administrator portal login flow."""
    next_path = _safe_next_path(next)

    if settings.auth_dev_bypass:
        request.session["portal_auth"] = {
            "email": "dev-admin@localhost",
            "subject": "dev-admin",
            "name": "Dev Admin",
            "flow": "admin",
            "source": "dev_bypass",
            "authenticated_at": datetime.now(UTC).isoformat(),
        }
        return RedirectResponse(
            url=_frontend_url(next_path),
            status_code=302,
        )

    state = sign_state(
        {
            "purpose": "portal_auth",
            "next_path": next_path,
        }
    )
    authentik = AuthentikService()
    redirect_url = authentik.create_login_redirect(
        callback_url=_backend_admin_callback_url(),
        state=state,
        flow="admin",
    )
    return RedirectResponse(url=redirect_url, status_code=302)


@router.get("/auth/callback")
def complete_portal_login(
    request: Request,
    state: str = Query(min_length=1),
    code: str | None = Query(default=None),
) -> RedirectResponse:
    """Complete administrator portal login callback."""
    try:
        payload = verify_state(
            state,
            max_age_seconds=max(60, settings.auth_state_ttl_minutes * 60),
        )
        if payload.get("purpose") != "portal_auth":
            raise ValueError("Invalid auth flow state")
        next_path = _safe_next_path(str(payload.get("next_path") or "/"))
    except Exception:  # noqa: BLE001
        return RedirectResponse(
            url=_frontend_url("/", query={"auth_error": "invalid_state"}),
            status_code=302,
        )

    authentik = AuthentikService()
    try:
        identity = authentik.validate_callback(
            code=code,
            state=state,
            request_params=dict(request.query_params),
            flow="admin",
        )
    except Exception:  # noqa: BLE001
        return RedirectResponse(
            url=_frontend_url("/", query={"auth_error": "login_failed"}),
            status_code=302,
        )

    request.session["portal_auth"] = {
        "email": str(identity.get("email") or ""),
        "subject": str(identity.get("subject") or ""),
        "name": str(identity.get("name") or ""),
        "flow": "admin",
        "source": "session",
        "authenticated_at": datetime.now(UTC).isoformat(),
    }
    return RedirectResponse(url=_frontend_url(next_path), status_code=302)


@router.post("/auth/logout")
def logout_portal(request: Request) -> dict:
    """Clear portal authentication session."""
    request.session.pop("portal_auth", None)
    return {"ok": True}


@router.get("/auth/me")
def get_auth_me(principal=Depends(require_portal_auth)) -> dict:
    """Return authenticated portal principal."""
    return {
        "email": principal.email,
        "subject": principal.subject,
        "name": principal.name,
        "flow": principal.flow,
        "source": principal.source,
    }
