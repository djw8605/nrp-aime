"""Audit API endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.audit.service import AuditService

router = APIRouter()


@router.post('/run')
def run_audit(db: Session = Depends(get_db)) -> dict:
    """Run cross-service audit checks."""
    return AuditService().run(db)
