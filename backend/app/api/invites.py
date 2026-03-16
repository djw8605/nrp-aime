"""Invite onboarding API endpoints."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.invite import (
    InviteCreateRequest,
    InviteCreateResponse,
    InvitePreviewResponse,
)
from app.services.invites.service import InviteFlowError, InviteService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/projects/{project_id}/invites", response_model=InviteCreateResponse, status_code=201)
def create_project_invite(
    project_id: uuid.UUID,
    payload: InviteCreateRequest,
    db: Session = Depends(get_db),
) -> InviteCreateResponse:
    """Create a secure invite link for a project user."""
    svc = InviteService()
    try:
        result = svc.create_invite(
            db,
            project_id=project_id,
            email=str(payload.email),
            expires_in_hours=payload.expires_in_hours,
            invited_by=payload.invited_by,
            authentik_group_name=payload.authentik_group_name,
            redirect_path=payload.redirect_path,
            metadata=payload.metadata,
            send_email=payload.send_email,
        )
    except InviteFlowError as exc:
        status_code = 404 if exc.code == "project_not_found" else 400
        raise HTTPException(status_code=status_code, detail=exc.message) from exc

    return InviteCreateResponse(
        id=result.invite.id,
        project_id=result.invite.project_id,
        user_id=result.invite.user_id,
        email=result.invite.email,
        status=result.invite.status,
        expires_at=result.invite.expires_at,
        invite_url=result.invite_url,
        email_dispatched=payload.send_email,
    )


@router.get("/invites/preview", response_model=InvitePreviewResponse)
def preview_invite(
    token: str = Query(min_length=1),
    db: Session = Depends(get_db),
) -> InvitePreviewResponse:
    """Return safe preview details for an invite token."""
    svc = InviteService()
    preview = svc.preview_invite(db, token=token)
    return InvitePreviewResponse(**preview)


@router.get("/invites/accept")
def accept_invite(
    token: str = Query(min_length=1),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Validate invite and start Authentik login redirect flow."""
    svc = InviteService()
    try:
        login_redirect = svc.begin_accept_flow(db, token=token)
    except InviteFlowError as exc:
        try:
            svc.record_unbound_failure(
                db,
                event_type="invite_accept_failed",
                code=exc.code,
                message=exc.message,
            )
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to record invite accept failure event")
        logger.warning("Invite accept failed code=%s", exc.code)
        error_redirect = svc.error_redirect_url(error_code=exc.code)
        return RedirectResponse(url=error_redirect, status_code=302)

    return RedirectResponse(url=login_redirect, status_code=302)


@router.get("/invites/callback")
@router.get("/auth/invite/callback")
def invite_callback(
    request: Request,
    state: str = Query(min_length=1),
    code: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Complete invite flow after Authentik authentication callback."""
    svc = InviteService()
    callback_params = dict(request.query_params)

    try:
        result = svc.finalize_callback(
            db,
            state=state,
            code=code,
            callback_params=callback_params,
        )
        success_redirect = svc.success_redirect_url(result)
        return RedirectResponse(url=success_redirect, status_code=302)
    except InviteFlowError as exc:
        try:
            svc.record_unbound_failure(
                db,
                event_type="invite_callback_failed",
                code=exc.code,
                message=exc.message,
                payload={"query_keys": sorted(list(callback_params.keys()))},
            )
        except Exception:  # noqa: BLE001
            db.rollback()
            logger.exception("Failed to record invite callback failure event")
        logger.warning("Invite callback failed code=%s", exc.code)
        error_redirect = svc.error_redirect_url(error_code=exc.code)
        return RedirectResponse(url=error_redirect, status_code=302)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("Invite callback failed due to unexpected error")
        error_redirect = svc.error_redirect_url(error_code="internal_error")
        return RedirectResponse(url=error_redirect, status_code=302)
