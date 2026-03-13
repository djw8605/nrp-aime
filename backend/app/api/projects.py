"""Project API endpoints."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.schemas.project import ProjectRead, ProjectReadWithUsers, ProjectUsage
from app.schemas.user import UserRead
from app.services.authentik.service import send_account_creation_email
from app.services.prometheus.service import PrometheusService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    """Return all projects."""
    return db.query(Project).all()


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> Project:
    """Return a single project by ID."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/users", response_model=list[UserRead])
def get_project_users(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return users assigned to a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return [pu.user for pu in project.project_users]


@router.get("/{project_id}/usage", response_model=ProjectUsage)
def get_project_usage(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectUsage:
    """Return CPU and GPU usage for a project from Prometheus."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    svc = PrometheusService()
    return svc.get_usage(project)


@router.post("/{project_id}/send-account-email")
def send_account_email(
    project_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger account creation emails for all users in a project (stub)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    for pu in project.project_users:
        background_tasks.add_task(
            send_account_creation_email, str(project_id), pu.user.email
        )

    logger.info("Queued account creation emails for project %s", project_id)
    return {"message": "Account creation emails queued successfully"}
