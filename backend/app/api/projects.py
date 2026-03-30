"""Project API endpoints."""

import logging
import re
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import cast, case, func, or_
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.amie_allocation_packet import AMIEAllocationPacket
from app.models.amie_lifecycle_packet import AMIELifecyclePacket
from app.models.amie_packet import AMIEPacket
from app.models.project import Project
from app.models.project_invite import ProjectInvite
from app.models.project_invite_event import ProjectInviteEvent
from app.models.project_usage_snapshot import ProjectUsageSnapshot
from app.models.user import User
from app.models.project_user import ProjectUser
from app.schemas.packets import EntityPacketRead
from app.schemas.project import (
    ProjectRead,
    ProjectSummary,
    ProjectUpdate,
    ProjectUsage,
)
from app.schemas.user import ProjectMemberCreate, ProjectMemberRead
from app.services.account_lifecycle import AccountLifecycleService
from app.services.accounting.service import AccountingService
from app.services.invites.service import InviteService
from app.services.project_provisioning import ProjectProvisioningService
from app.services.prometheus.service import PrometheusService

logger = logging.getLogger(__name__)
router = APIRouter()


def _clean_string(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_tags(tags: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in tags or []:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(cleaned)
    return normalized


def _has_debug_tag(tags: list[str] | None) -> bool:
    return "debug" in {item.lower() for item in _normalize_tags(tags)}


def _role_is_pi(role: str | None) -> bool:
    return str(role or "").strip().lower() == "pi"


def _full_name(
    first_name: str | None,
    middle_name: str | None,
    last_name: str | None,
) -> str:
    return " ".join(
        part.strip()
        for part in [first_name, middle_name, last_name]
        if part and part.strip()
    ).strip()


def _to_project_member_read(db: Session, membership: ProjectUser) -> ProjectMemberRead:
    lifecycle = AccountLifecycleService()
    account_confirmation_required = lifecycle.account_confirmation_required(
        db, membership
    )
    return ProjectMemberRead(
        project_user_id=membership.id,
        id=membership.user.id,
        email=membership.user.email,
        name=membership.user.name,
        tags=membership.user.tags or [],
        first_name=membership.user.first_name,
        middle_name=membership.user.middle_name,
        last_name=membership.user.last_name,
        person_id=membership.user.person_id,
        global_id=membership.user.global_id,
        organization=membership.user.organization,
        org_code=membership.user.org_code,
        department=membership.user.department,
        nsf_status_code=membership.user.nsf_status_code,
        dn_list=membership.user.dn_list or [],
        user_is_active=membership.user.is_active,
        account_is_active=membership.is_active,
        account_state=membership.account_state,
        account_state_updated_at=membership.account_state_updated_at,
        email_sent_at=membership.email_sent_at,
        account_made_at=membership.account_made_at,
        aime_confirmation_sent_at=membership.aime_confirmation_sent_at,
        source_packet_rec_id=membership.source_packet_rec_id,
        source_trans_rec_id=membership.source_trans_rec_id,
        source_transaction_id=membership.source_transaction_id,
        role=membership.role,
        is_project_pi=_role_is_pi(membership.role),
        account_confirmation_required=account_confirmation_required,
        account_confirmation_via=(
            "notify_account_create"
            if account_confirmation_required
            else "notify_project_create"
        ),
        resource=membership.resource,
        allocated_resource=membership.allocated_resource,
        membership_service_units_allocated=(
            float(membership.service_units_allocated)
            if membership.service_units_allocated is not None
            else None
        ),
        membership_service_units_remaining=(
            float(membership.service_units_remaining)
            if membership.service_units_remaining is not None
            else None
        ),
        account_remote_site_login=membership.remote_site_login,
        source_site_name=membership.user.source_site_name,
        service_units_allocated=(
            float(membership.user.service_units_allocated)
            if membership.user.service_units_allocated is not None
            else None
        ),
        created_at=membership.user.created_at,
    )


def _to_entity_packet_read(packet: AMIEPacket, *, matched_on: list[str]) -> EntityPacketRead:
    return EntityPacketRead(
        id=packet.id,
        packet_rec_id=packet.packet_rec_id,
        trans_rec_id=packet.trans_rec_id,
        transaction_id=packet.transaction_id,
        packet_type=packet.packet_type,
        processing_status=packet.processing_status,
        processing_error=packet.processing_error,
        ingest_source=packet.ingest_source,
        received_at=packet.created_at,
        processed_at=packet.processed_at,
        matched_on=matched_on,
    )


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
        allocation_record_id=project.allocation_record_id,
        site_project_id=project.site_project_id,
        allocation_type=project.allocation_type,
        request_type=project.request_type,
        source_packet_rec_id=project.source_packet_rec_id,
        source_trans_rec_id=project.source_trans_rec_id,
        source_transaction_id=project.source_transaction_id,
        source_site_name=project.source_site_name,
        tags=project.tags or [],
        allocated_resource=project.allocated_resource,
        service_units_allocated=(
            float(project.service_units_allocated)
            if project.service_units_allocated is not None
            else None
        ),
        service_units_remaining=(
            float(project.service_units_remaining)
            if project.service_units_remaining is not None
            else None
        ),
        start_date=project.start_date,
        end_date=project.end_date,
        project_title=project.project_title,
        pfos_number=project.pfos_number,
        board_type=project.board_type,
        pi_person_id=project.pi_person_id,
        pi_first_name=project.pi_first_name,
        pi_middle_name=project.pi_middle_name,
        pi_last_name=project.pi_last_name,
        pi_email=project.pi_email,
        pi_organization=project.pi_organization,
        pi_org_code=project.pi_org_code,
        pi_department=project.pi_department,
        pi_business_phone_number=project.pi_business_phone_number,
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
        lifecycle_state=project.lifecycle_state,
        provisioning_state=project.provisioning_state,
        provisioning_requested_at=project.provisioning_requested_at,
        provisioning_started_at=project.provisioning_started_at,
        provisioning_completed_at=project.provisioning_completed_at,
        provisioning_last_error=project.provisioning_last_error,
        provisioning_alerted_at=project.provisioning_alerted_at,
        created_at=project.created_at,
    )


@router.get("/", response_model=list[ProjectRead])
def list_projects(
    include_debug: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[ProjectRead]:
    """Return all projects with allocated and current usage values."""
    accounting = AccountingService()
    projects = db.query(Project).options(joinedload(Project.usage_snapshot)).all()
    visible_projects = projects if include_debug else [
        project for project in projects if not _has_debug_tag(project.tags)
    ]
    return [
        _to_project_read(db, project=project, accounting=accounting)
        for project in visible_projects
    ]


@router.get("/summary", response_model=ProjectSummary)
def get_projects_summary(db: Session = Depends(get_db)) -> ProjectSummary:
    """Return aggregate KPIs across all projects from persisted usage snapshots."""
    # Filter out debug-tagged projects/users at the SQL level using a JSONB
    # containment check. The 'debug' tag is always stored lowercase by
    # _normalize_tags, so a case-sensitive check is sufficient.
    non_debug_project = ~cast(Project.tags, JSONB).contains(["debug"])
    non_debug_user = ~cast(User.tags, JSONB).contains(["debug"])

    proj_stats = (
        db.query(
            func.count(Project.id).label("total"),
            func.sum(case((Project.is_active, 1), else_=0)).label("active"),
            func.coalesce(func.sum(Project.cpu_allocated), 0).label("cpu_allocated"),
            func.coalesce(func.sum(Project.gpu_allocated), 0).label("gpu_allocated"),
            func.sum(
                case((Project.service_units_allocated.isnot(None), 1), else_=0)
            ).label("with_su"),
            func.coalesce(func.sum(Project.service_units_allocated), 0).label("total_su"),
            func.coalesce(func.sum(ProjectUsageSnapshot.cpu_used_current), 0).label("cpu_used"),
            func.coalesce(func.sum(ProjectUsageSnapshot.gpu_used_current), 0).label("gpu_used"),
        )
        .outerjoin(ProjectUsageSnapshot, ProjectUsageSnapshot.project_id == Project.id)
        .filter(non_debug_project)
        .one()
    )

    user_stats = (
        db.query(
            func.count(User.id).label("total"),
            func.sum(case((User.is_active, 1), else_=0)).label("active"),
        )
        .filter(non_debug_user)
        .one()
    )

    return ProjectSummary(
        total_projects=proj_stats.total or 0,
        active_projects=proj_stats.active or 0,
        total_users=user_stats.total or 0,
        active_users=user_stats.active or 0,
        total_cpu_allocated=int(proj_stats.cpu_allocated or 0),
        total_gpu_allocated=int(proj_stats.gpu_allocated or 0),
        total_cpu_used=float(proj_stats.cpu_used or 0),
        total_gpu_used=float(proj_stats.gpu_used or 0),
        projects_with_service_units=int(proj_stats.with_su or 0),
        total_service_units_allocated=float(proj_stats.total_su or 0),
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


@router.get("/{project_id}/packets", response_model=list[EntityPacketRead])
def get_project_packets(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[EntityPacketRead]:
    """Return packets that created or modified a project's values."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    packet_matches: dict[uuid.UUID, dict[str, object]] = {}

    def add_packet(packet: AMIEPacket | None, reason: str) -> None:
        if packet is None:
            return
        existing = packet_matches.get(packet.id)
        if existing is None:
            packet_matches[packet.id] = {"packet": packet, "matched_on": [reason]}
            return
        matched_on = existing["matched_on"]
        if isinstance(matched_on, list) and reason not in matched_on:
            matched_on.append(reason)

    def add_packets(rows: list[AMIEPacket], reason: str) -> None:
        for row in rows:
            add_packet(row, reason)

    if project.source_packet_rec_id is not None:
        add_packet(
            db.query(AMIEPacket)
            .filter(AMIEPacket.packet_rec_id == project.source_packet_rec_id)
            .first(),
            "project.source_packet_rec_id",
        )
    if project.source_trans_rec_id is not None:
        add_packets(
            db.query(AMIEPacket)
            .filter(AMIEPacket.trans_rec_id == project.source_trans_rec_id)
            .all(),
            "project.source_trans_rec_id",
        )
    if project.source_transaction_id is not None:
        add_packets(
            db.query(AMIEPacket)
            .filter(AMIEPacket.transaction_id == project.source_transaction_id)
            .all(),
            "project.source_transaction_id",
        )
    if project.grant_number:
        add_packets(
            db.query(AMIEPacket)
            .join(AMIEAllocationPacket, AMIEAllocationPacket.packet_id == AMIEPacket.id)
            .filter(AMIEAllocationPacket.grant_number == project.grant_number)
            .all(),
            "allocation.grant_number",
        )
        add_packets(
            db.query(AMIEPacket)
            .join(AMIELifecyclePacket, AMIELifecyclePacket.packet_id == AMIEPacket.id)
            .filter(AMIELifecyclePacket.grant_number == project.grant_number)
            .all(),
            "lifecycle.grant_number",
        )
    if project.allocation_record_id:
        add_packets(
            db.query(AMIEPacket)
            .join(AMIEAllocationPacket, AMIEAllocationPacket.packet_id == AMIEPacket.id)
            .filter(AMIEAllocationPacket.record_id == project.allocation_record_id)
            .all(),
            "allocation.record_id",
        )
    if project.site_project_id:
        add_packets(
            db.query(AMIEPacket)
            .join(AMIEAllocationPacket, AMIEAllocationPacket.packet_id == AMIEPacket.id)
            .filter(AMIEAllocationPacket.project_id == project.site_project_id)
            .all(),
            "allocation.project_id",
        )
        add_packets(
            db.query(AMIEPacket)
            .join(AMIELifecyclePacket, AMIELifecyclePacket.packet_id == AMIEPacket.id)
            .filter(AMIELifecyclePacket.project_id == project.site_project_id)
            .all(),
            "lifecycle.project_id",
        )

    ordered = sorted(
        packet_matches.values(),
        key=lambda item: (
            getattr(item["packet"], "created_at", None) is not None,
            getattr(item["packet"], "created_at", None),
            getattr(item["packet"], "packet_rec_id", 0) or 0,
        ),
        reverse=True,
    )
    return [
        _to_entity_packet_read(
            item["packet"],
            matched_on=list(item["matched_on"]),
        )
        for item in ordered
        if isinstance(item.get("packet"), AMIEPacket)
    ]


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectRead:
    """Update a project's stored details."""
    project = (
        db.query(Project)
        .options(joinedload(Project.usage_snapshot))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        accounting = AccountingService()
        return _to_project_read(db, project=project, accounting=accounting)

    string_fields = (
        "grant_number",
        "allocation_record_id",
        "site_project_id",
        "allocation_type",
        "request_type",
        "source_site_name",
        "allocated_resource",
        "project_title",
        "pfos_number",
        "board_type",
        "pi_person_id",
        "pi_first_name",
        "pi_middle_name",
        "pi_last_name",
        "pi_email",
        "pi_organization",
        "pi_org_code",
        "pi_department",
        "pi_business_phone_number",
        "resource_type",
        "kubernetes_namespace",
        "authentik_group_name",
        "provisioning_last_error",
    )
    for field in string_fields:
        if field in updates:
            setattr(project, field, _clean_string(updates[field]))

    if "tags" in updates:
        project.tags = _normalize_tags(updates["tags"])

    required_string_fields = ("aime_allocation_id", "name", "lifecycle_state", "provisioning_state")
    for field in required_string_fields:
        if field in updates:
            cleaned = _clean_string(updates[field])
            if not cleaned:
                raise HTTPException(
                    status_code=400,
                    detail=f"{field} cannot be empty",
                )
            setattr(project, field, cleaned)

    passthrough_fields = (
        "source_packet_rec_id",
        "source_trans_rec_id",
        "source_transaction_id",
        "service_units_allocated",
        "service_units_remaining",
        "start_date",
        "end_date",
        "cpu_allocated",
        "gpu_allocated",
        "provisioning_requested_at",
        "provisioning_started_at",
        "provisioning_completed_at",
        "provisioning_alerted_at",
    )
    for field in passthrough_fields:
        if field in updates:
            setattr(project, field, updates[field])

    if "is_active" in updates:
        project.is_active = bool(updates["is_active"])

    db.commit()
    db.refresh(project)

    accounting = AccountingService()
    return _to_project_read(db, project=project, accounting=accounting)


@router.get("/{project_id}/users", response_model=list[ProjectMemberRead])
def get_project_users(project_id: uuid.UUID, db: Session = Depends(get_db)):
    """Return users assigned to a project."""
    project = (
        db.query(Project)
        .options(joinedload(Project.project_users).joinedload(ProjectUser.user))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return [_to_project_member_read(db, pu) for pu in project.project_users]


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=201)
def add_project_member(
    project_id: uuid.UUID,
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
) -> ProjectMemberRead:
    """Add an existing or brand-new person to a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    has_existing_user = payload.existing_user_id is not None
    has_new_user = payload.new_user is not None
    if has_existing_user == has_new_user:
        raise HTTPException(
            status_code=400,
            detail="Provide either existing_user_id or new_user",
        )

    if payload.existing_user_id is not None:
        user = db.query(User).filter(User.id == payload.existing_user_id).first()
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
    else:
        new_user = payload.new_user
        if new_user is None:
            raise HTTPException(status_code=400, detail="new_user payload is required")

        email = _clean_string(str(new_user.email) if new_user.email else None)
        if email:
            existing = db.query(User).filter(User.email == email).first()
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="A user with this email already exists. Choose the existing person instead.",
                )

        user_name = _clean_string(new_user.name) or _full_name(
            new_user.first_name,
            new_user.middle_name,
            new_user.last_name,
        )
        if not user_name:
            raise HTTPException(
                status_code=400,
                detail="New people require a name or first/last name",
            )

        user = User(
            email=email,
            name=user_name,
            tags=_normalize_tags(new_user.tags),
            first_name=_clean_string(new_user.first_name),
            middle_name=_clean_string(new_user.middle_name),
            last_name=_clean_string(new_user.last_name),
            person_id=_clean_string(new_user.person_id),
            global_id=_clean_string(new_user.global_id),
            organization=_clean_string(new_user.organization),
            org_code=_clean_string(new_user.org_code),
            department=_clean_string(new_user.department),
            nsf_status_code=_clean_string(new_user.nsf_status_code),
            dn_list=[
                item.strip()
                for item in (new_user.dn_list or [])
                if isinstance(item, str) and item.strip()
            ],
            remote_site_login=_clean_string(new_user.remote_site_login),
            source_site_name=_clean_string(new_user.source_site_name),
            service_units_allocated=new_user.service_units_allocated,
            is_active=bool(new_user.is_active),
        )
        db.add(user)
        db.flush()

    membership_resource = _clean_string(payload.resource)
    duplicate_membership = (
        db.query(ProjectUser)
        .filter(
            ProjectUser.project_id == project.id,
            ProjectUser.user_id == user.id,
        )
        .filter(
            ProjectUser.resource == membership_resource
            if membership_resource
            else or_(ProjectUser.resource.is_(None), ProjectUser.resource == "")
        )
        .first()
    )
    if duplicate_membership is not None:
        raise HTTPException(
            status_code=409,
            detail="This person is already attached to the project for that resource",
        )

    membership = ProjectUser(
        project_id=project.id,
        user_id=user.id,
        role=_clean_string(payload.role),
        resource=membership_resource,
        allocated_resource=_clean_string(payload.allocated_resource),
        service_units_allocated=payload.membership_service_units_allocated,
        service_units_remaining=payload.membership_service_units_remaining,
        remote_site_login=_clean_string(payload.account_remote_site_login),
        is_active=bool(payload.account_is_active),
        source_packet_rec_id=payload.source_packet_rec_id,
        source_trans_rec_id=payload.source_trans_rec_id,
        source_transaction_id=payload.source_transaction_id,
    )
    requested_account_state = _clean_string(payload.account_state)
    if requested_account_state:
        try:
            membership.set_account_state(requested_account_state)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.add(membership)
    db.commit()

    membership = (
        db.query(ProjectUser)
        .options(joinedload(ProjectUser.user))
        .filter(ProjectUser.id == membership.id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=500, detail="Failed to create project membership")
    return _to_project_member_read(db, membership)


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
            membership.account_state not in (
                ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
                ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
                ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT,
            )
            for membership in relevant_memberships
        )
        if not needs_invite:
            skipped += 1
            continue

        try:
            for membership in relevant_memberships:
                if membership.account_state == ProjectUser.ACCOUNT_STATE_RECEIVED:
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


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    """Soft-delete a project by marking it inactive.

    Does not affect user records; only the project is deactivated.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.is_active = False
    db.commit()
    logger.info("Project soft-deleted project_id=%s name=%r", project_id, project.name)


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


# ---------------------------------------------------------------------------
# Debug / mock endpoints — bypass external services for development
# ---------------------------------------------------------------------------

_SAFE_NS = re.compile(r"[^a-z0-9-]+")


@router.post("/{project_id}/debug-provision")
def debug_provision_project(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Mock-provision a project without contacting the NRP portal.

    Generates a namespace name using the same logic as the real
    provisioning service, writes it to the database, and advances the
    project lifecycle to ``provisioned`` (or ``waiting_pi_account`` if
    the PI still needs to onboard).
    """
    project = db.query(Project).options(
        joinedload(Project.project_users)
    ).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    now = datetime.now(UTC)

    # Generate namespace name using the same deterministic logic.
    if project.kubernetes_namespace:
        namespace = project.kubernetes_namespace
    else:
        seed = (
            project.site_project_id
            or project.grant_number
            or project.aime_allocation_id
            or str(project.id)
        )
        fragment = _SAFE_NS.sub("-", seed.strip().lower()).strip("-")[:63] or "project"
        namespace = f"nrp-{fragment}"

    # Fill in infrastructure fields as if portal RPC succeeded.
    project.kubernetes_namespace = namespace
    project.authentik_group_name = namespace
    project.provisioning_state = Project.PROVISIONING_STATE_READY
    project.provisioning_started_at = now
    project.provisioning_completed_at = now
    project.provisioning_last_error = None
    if project.provisioning_requested_at is None:
        project.provisioning_requested_at = now

    # Walk lifecycle through the intermediate states so set_lifecycle_state
    # validation passes regardless of the current state.
    if project.lifecycle_state == Project.LIFECYCLE_STATE_RECEIVED:
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PENDING_PROVISIONING)
    if project.lifecycle_state == Project.LIFECYCLE_STATE_PENDING_PROVISIONING:
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONING)
    if project.lifecycle_state in (
        Project.LIFECYCLE_STATE_PROVISIONING,
        Project.LIFECYCLE_STATE_PROVISIONING_FAILED,
    ):
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONED)

    # Check if PI still needs to onboard.
    if project.lifecycle_state == Project.LIFECYCLE_STATE_PROVISIONED:
        if ProjectProvisioningService._has_pending_pi_account(project):
            project.set_lifecycle_state(Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT)

    db.commit()
    db.refresh(project)

    logger.info(
        "Debug-provisioned project project_id=%s namespace=%s lifecycle=%s",
        project.id,
        namespace,
        project.lifecycle_state,
    )
    return {
        "ok": True,
        "debug": True,
        "project_id": str(project.id),
        "kubernetes_namespace": namespace,
        "authentik_group_name": namespace,
        "lifecycle_state": project.lifecycle_state,
        "provisioning_state": project.provisioning_state,
    }


def _create_mock_invite_for_confirmation(
    db: Session,
    user: User,
    project_user: ProjectUser,
    project: Project,
    now: datetime,
) -> None:
    """Create a mock ProjectInvite record to satisfy AIME confirmation checks.

    The mock OAuth flow bypasses the normal email invite process, so we need
    to create the invite record and event that _invite_completion_allows_confirmation()
    expects in order to send the notify_account_create packet back to AIME.
    """
    invite = ProjectInvite(
        project_id=project.id,
        user_id=user.id,
        email=user.email or "",
        token_hash="mock-oauth-bypass",
        status=ProjectInvite.STATUS_USED,
        expires_at=now,
        used_at=now,
        invited_by="mock-oauth-debug",
    )
    db.add(invite)
    db.flush()

    event = ProjectInviteEvent(
        invite_id=invite.id,
        event_type="invite_email_dispatched",
        event_status="info",
        message="Mock OAuth bypass: email dispatched",
        event_payload={"mock": True, "debug": True},
    )
    db.add(event)


@router.post("/{project_id}/users/{project_user_id}/debug-complete-account")
def debug_complete_user_account(
    project_id: uuid.UUID,
    project_user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Mock a user completing the OAuth onboarding flow.

    Bypasses email invite and Authentik OAuth. Generates a mock
    ``remote_site_login``, advances the account state to
    ``user_completed_oauth``, and — if the user is a PI — advances
    the project lifecycle past the ``waiting_pi_account`` gate.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    pu = (
        db.query(ProjectUser)
        .filter(
            ProjectUser.id == project_user_id,
            ProjectUser.project_id == project_id,
        )
        .first()
    )
    if not pu:
        raise HTTPException(status_code=404, detail="Project user not found")

    user = db.query(User).filter(User.id == pu.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.now(UTC)

    # Generate a mock remote_site_login from the user's email or name.
    mock_login = (
        (user.email or "").split("@")[0]
        or (user.name or "").replace(" ", ".").lower()
        or f"debug-user-{str(user.id)[:8]}"
    )

    # Update User record as if Authentik OAuth returned this identity.
    user.remote_site_login = mock_login
    user.is_active = True

    # Update ProjectUser record — walk through intermediate states.
    pu.remote_site_login = mock_login
    pu.is_active = True

    if pu.account_state == ProjectUser.ACCOUNT_STATE_RECEIVED:
        pu.set_account_state(ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT)
        pu.email_sent_at = now

    if pu.account_state == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT:
        pu.set_account_state(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
        pu.account_made_at = now
        _create_mock_invite_for_confirmation(db, user, pu, project, now)

    # If user is PI, advance project past waiting_pi_account.
    is_pi = str(pu.role or "").strip().lower() == "pi"
    if is_pi and project.lifecycle_state == Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT:
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONED)

    db.commit()

    logger.info(
        "Debug-completed user account project_user_id=%s mock_login=%s is_pi=%s",
        pu.id,
        mock_login,
        is_pi,
    )
    return {
        "ok": True,
        "debug": True,
        "project_user_id": str(pu.id),
        "user_id": str(user.id),
        "remote_site_login": mock_login,
        "account_state": pu.account_state,
        "project_lifecycle_state": project.lifecycle_state,
    }
