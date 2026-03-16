"""Audit API endpoints."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.audit.service import AuditService

router = APIRouter()


class AuthentikSyncRequest(BaseModel):
    """Payload for Authentik membership reconciliation."""

    apply_changes: bool = False


class PortalSyncRequest(BaseModel):
    """Payload for portal namespace/membership reconciliation."""

    apply_changes: bool = False


@router.post('/run')
def run_audit(db: Session = Depends(get_db)) -> dict:
    """Run cross-service audit checks."""
    return AuditService().run(db)


@router.post('/authentik-sync')
def sync_authentik_memberships(
    payload: AuthentikSyncRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Audit and optionally reconcile Authentik memberships against DB."""
    return AuditService().sync_authentik_memberships(
        db,
        apply_changes=payload.apply_changes,
    )


@router.post('/portal-sync')
def sync_portal_namespace_memberships(
    payload: PortalSyncRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Audit and optionally reconcile portal namespace memberships against DB."""
    return AuditService().sync_portal_namespace_memberships(
        db,
        apply_changes=payload.apply_changes,
    )
