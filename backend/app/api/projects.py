"""Project API endpoints."""

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.project import Project
from app.models.project_usage_snapshot import ProjectUsageSnapshot
from app.models.user import User
from app.models.project_user import ProjectUser
from app.schemas.project import (
    ProjectRead,
    ProjectSummary,
    ProjectUsage,
)
from app.schemas.user import ProjectMemberRead
from app.services.account_lifecycle import AccountLifecycleService
from app.services.authentik.service import send_account_creation_email
from app.services.prometheus.service import PrometheusService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    """Return all projects."""
    return db.query(Project).all()


@router.get("/summary", response_model=ProjectSummary)
def get_projects_summary(db: Session = Depends(get_db)) -> ProjectSummary:
    """Return aggregate KPIs across all projects from persisted usage snapshots."""
    total_projects = db.query(Project).count()
    active_projects = db.query(Project).filter(Project.is_active.is_(True)).count()
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active.is_(True)).count()
    total_cpu_used, total_gpu_used = db.query(
        func.coalesce(func.sum(ProjectUsageSnapshot.cpu_used_current), 0),
        func.coalesce(func.sum(ProjectUsageSnapshot.gpu_used_current), 0),
    ).one()

    return ProjectSummary(
        total_projects=total_projects,
        active_projects=active_projects,
        total_users=total_users,
        active_users=active_users,
        total_cpu_used=float(total_cpu_used),
        total_gpu_used=float(total_gpu_used),
    )


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> Project:
    """Return a single project by ID."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/{project_id}/users", response_model=list[ProjectMemberRead])
def get_project_users(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return users assigned to a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return [
        ProjectMemberRead(
            id=pu.user.id,
            email=pu.user.email,
            name=pu.user.name,
            first_name=pu.user.first_name,
            middle_name=pu.user.middle_name,
            last_name=pu.user.last_name,
            person_id=pu.user.person_id,
            organization=pu.user.organization,
            department=pu.user.department,
            nsf_status_code=pu.user.nsf_status_code,
            dn_list=pu.user.dn_list or [],
            user_is_active=pu.user.is_active,
            account_is_active=pu.is_active,
            account_state=pu.account_state,
            account_state_updated_at=pu.account_state_updated_at,
            email_sent_at=pu.email_sent_at,
            account_made_at=pu.account_made_at,
            aime_confirmation_sent_at=pu.aime_confirmation_sent_at,
            source_packet_rec_id=pu.source_packet_rec_id,
            source_trans_rec_id=pu.source_trans_rec_id,
            source_transaction_id=pu.source_transaction_id,
            role=pu.role,
            resource=pu.resource,
            account_remote_site_login=pu.remote_site_login,
            created_at=pu.user.created_at,
        )
        for pu in project.project_users
    ]


@router.get("/{project_id}/usage", response_model=ProjectUsage)
def get_project_usage(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectUsage:
    """Return CPU and GPU usage for a project from persisted snapshots."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    snapshot = (
        db.query(ProjectUsageSnapshot)
        .filter(ProjectUsageSnapshot.project_id == project.id)
        .first()
    )
    if snapshot is not None:
        return ProjectUsage(
            cpu_allocated=project.cpu_allocated,
            cpu_used=float(snapshot.cpu_used_current),
            gpu_allocated=project.gpu_allocated,
            gpu_used=float(snapshot.gpu_used_current),
        )

    # Fallback for brand-new environments before the usage worker has run.
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

    lifecycle = AccountLifecycleService()
    queued = 0
    skipped = 0
    for pu in project.project_users:
        if pu.account_state == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE:
            skipped += 1
            continue
        if not pu.user.email:
            skipped += 1
            continue

        lifecycle.mark_email_sent(pu)
        background_tasks.add_task(
            send_account_creation_email, str(project_id), pu.user.email
        )
        queued += 1

    db.commit()
    logger.info(
        "Queued account creation emails for project %s queued=%s skipped=%s",
        project_id,
        queued,
        skipped,
    )
    return {
        "message": "Account creation emails queued successfully",
        "queued": queued,
        "skipped": skipped,
    }
