"""Project API endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

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
from app.services.accounting.service import AccountingService
from app.services.invites.service import InviteService
from app.services.project_provisioning import ProjectProvisioningService
from app.services.prometheus.service import PrometheusService

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_project_read(
    db: Session,
    *,
    project: Project,
    accounting: AccountingService,
) -> ProjectRead:
    cpu_used, gpu_used, usage_source, usage_last_collected_at = accounting.project_current_usage(
        db, project=project
    )
    return ProjectRead(
        id=project.id,
        aime_allocation_id=project.aime_allocation_id,
        name=project.name,
        grant_number=project.grant_number,
        site_project_id=project.site_project_id,
        allocation_type=project.allocation_type,
        request_type=project.request_type,
        source_packet_rec_id=project.source_packet_rec_id,
        source_trans_rec_id=project.source_trans_rec_id,
        source_transaction_id=project.source_transaction_id,
        resource_type=project.resource_type,
        cpu_allocated=project.cpu_allocated,
        gpu_allocated=project.gpu_allocated,
        cpu_used_current=cpu_used,
        gpu_used_current=gpu_used,
        usage_source=usage_source,
        usage_last_collected_at=usage_last_collected_at,
        is_active=project.is_active,
        kubernetes_namespace=project.kubernetes_namespace,
        authentik_group_name=project.authentik_group_name,
        provisioning_state=project.provisioning_state,
        provisioning_requested_at=project.provisioning_requested_at,
        provisioning_started_at=project.provisioning_started_at,
        provisioning_completed_at=project.provisioning_completed_at,
        provisioning_last_error=project.provisioning_last_error,
        provisioning_alerted_at=project.provisioning_alerted_at,
        created_at=project.created_at,
    )


@router.get("/", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)) -> list[ProjectRead]:
    """Return all projects with allocated and current usage values."""
    accounting = AccountingService()
    projects = db.query(Project).options(joinedload(Project.usage_snapshot)).all()
    return [_to_project_read(db, project=project, accounting=accounting) for project in projects]


@router.get("/summary", response_model=ProjectSummary)
def get_projects_summary(db: Session = Depends(get_db)) -> ProjectSummary:
    """Return aggregate KPIs across all projects from persisted usage snapshots."""
    total_projects = db.query(Project).count()
    active_projects = db.query(Project).filter(Project.is_active.is_(True)).count()
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active.is_(True)).count()
    total_cpu_allocated, total_gpu_allocated = db.query(
        func.coalesce(func.sum(Project.cpu_allocated), 0),
        func.coalesce(func.sum(Project.gpu_allocated), 0),
    ).one()
    total_cpu_used, total_gpu_used = db.query(
        func.coalesce(func.sum(ProjectUsageSnapshot.cpu_used_current), 0),
        func.coalesce(func.sum(ProjectUsageSnapshot.gpu_used_current), 0),
    ).one()

    return ProjectSummary(
        total_projects=total_projects,
        active_projects=active_projects,
        total_users=total_users,
        active_users=active_users,
        total_cpu_allocated=int(total_cpu_allocated),
        total_gpu_allocated=int(total_gpu_allocated),
        total_cpu_used=float(total_cpu_used),
        total_gpu_used=float(total_gpu_used),
    )


@router.post("/accounting/stub-sync")
def refresh_accounting_stub_data(db: Session = Depends(get_db)) -> dict:
    """Populate stub accounting snapshots for projects without live accounting data."""
    accounting = AccountingService()
    result = accounting.refresh_all_stub_snapshots(db)
    return {
        "message": "Accounting stub data refreshed",
        "stub_enabled": accounting.stub_enabled,
        **result,
    }


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ProjectRead:
    """Return a single project by ID."""
    project = (
        db.query(Project)
        .options(joinedload(Project.usage_snapshot))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    accounting = AccountingService()
    return _to_project_read(db, project=project, accounting=accounting)


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

    accounting = AccountingService()
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
            usage_source="usage_snapshot",
            usage_last_collected_at=snapshot.last_collected_at,
        )

    if accounting.stub_enabled:
        cpu_used, gpu_used, usage_source, usage_last_collected_at = (
            accounting.project_current_usage(db, project=project)
        )
        return ProjectUsage(
            cpu_allocated=project.cpu_allocated,
            cpu_used=cpu_used,
            gpu_allocated=project.gpu_allocated,
            gpu_used=gpu_used,
            usage_source=usage_source,
            usage_last_collected_at=usage_last_collected_at,
            usage_note="Stub accounting data",
        )

    # Fallback for brand-new environments before the usage worker has run.
    svc = PrometheusService()
    usage = svc.get_usage(project)
    usage.usage_source = "prometheus_live"
    usage.usage_note = "Live Prometheus query fallback"
    return usage


@router.post("/{project_id}/send-account-email")
def send_account_email(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
):
    """Generate person-scoped invite links for project users."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    lifecycle = AccountLifecycleService()
    invites = InviteService()
    queued = 0
    skipped = 0
    failed = 0
    invited_user_ids: set[uuid.UUID] = set()
    for pu in project.project_users:
        if pu.user_id in invited_user_ids:
            continue
        if not pu.user.email:
            skipped += 1
            continue

        relevant_memberships = [
            membership
            for membership in pu.user.project_users
            if membership.is_active
        ]
        if not relevant_memberships:
            skipped += 1
            continue

        needs_invite = any(
            membership.account_state != ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE
            for membership in relevant_memberships
        )
        if not needs_invite:
            skipped += 1
            continue

        try:
            for membership in relevant_memberships:
                if membership.account_state != ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE:
                    lifecycle.mark_email_sent(membership)
            invites.create_invite(
                db,
                user_id=pu.user_id,
                email=pu.user.email,
                invited_by="system:send-account-email",
                metadata={
                    "trigger_project_id": str(project.id),
                    "trigger_project_user_id": str(pu.id),
                },
                send_email=True,
            )
            invited_user_ids.add(pu.user_id)
            queued += 1
        except Exception:  # noqa: BLE001
            db.rollback()
            failed += 1
            logger.exception(
                "Failed to generate person invite for user=%s from project=%s",
                pu.user_id,
                project.id,
            )

    logger.info(
        "Queued invite emails for project %s queued=%s skipped=%s failed=%s",
        project_id,
        queued,
        skipped,
        failed,
    )
    return {
        "message": "Invite-based account emails queued",
        "queued": queued,
        "skipped": skipped,
        "failed": failed,
    }


@router.post("/{project_id}/provision-infrastructure")
def provision_project_infrastructure(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Create project namespace/group infrastructure via portal RPC."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    result = ProjectProvisioningService().provision_project(
        db,
        project=project,
        requested_by="admin:project-page",
    )
    if not result.get("ok", False):
        logger.warning(
            "Project provisioning failed project_id=%s result=%s",
            project_id,
            result,
        )
    return result
