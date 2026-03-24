"""User (person) API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.amie_lifecycle_packet import AMIELifecyclePacket
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.amie_packet import AMIEPacket
from app.models.project_user import ProjectUser
from app.models.user import User
from app.schemas.invite import InviteCreateResponse
from app.schemas.packets import EntityPacketRead
from app.schemas.user import (
    UserCreate,
    UserInviteCreate,
    UserPacketDetailRead,
    UserProjectMembershipRead,
    UserRead,
    UserUpdate,
)
from app.services.account_lifecycle import AccountLifecycleService
from app.services.invites.service import InviteService

router = APIRouter()


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


def _project_names_for_user(user: User, *, include_debug_projects: bool = True) -> list[str]:
    return sorted(
        {
            pu.project.name
            for pu in user.project_users
            if pu.project is not None and pu.project.name
            and (include_debug_projects or not _has_debug_tag(pu.project.tags))
        }
    )


def _role_is_pi(role: str | None) -> bool:
    return str(role or "").strip().lower() == "pi"


def _pi_project_names_for_user(
    user: User, *, include_debug_projects: bool = True
) -> list[str]:
    return sorted(
        {
            pu.project.name
            for pu in user.project_users
            if _role_is_pi(pu.role)
            and pu.project is not None
            and pu.project.name
            and (include_debug_projects or not _has_debug_tag(pu.project.tags))
        }
    )


def _to_user_read(user: User, *, include_debug_projects: bool = True) -> UserRead:
    project_names = _project_names_for_user(
        user,
        include_debug_projects=include_debug_projects,
    )
    pi_project_names = _pi_project_names_for_user(
        user,
        include_debug_projects=include_debug_projects,
    )
    return UserRead(
        id=user.id,
        email=user.email,
        name=user.name,
        tags=user.tags or [],
        first_name=user.first_name,
        middle_name=user.middle_name,
        last_name=user.last_name,
        person_id=user.person_id,
        global_id=user.global_id,
        organization=user.organization,
        org_code=user.org_code,
        department=user.department,
        nsf_status_code=user.nsf_status_code,
        dn_list=user.dn_list or [],
        remote_site_login=user.remote_site_login,
        source_site_name=user.source_site_name,
        service_units_allocated=(
            float(user.service_units_allocated)
            if user.service_units_allocated is not None
            else None
        ),
        is_active=user.is_active,
        project_count=len(project_names),
        project_names=project_names,
        is_pi=bool(pi_project_names),
        pi_project_count=len(pi_project_names),
        pi_project_names=pi_project_names,
        created_at=user.created_at,
    )


def _membership_confirmation_context(
    db: Session,
    membership: ProjectUser,
) -> tuple[bool, str]:
    lifecycle = AccountLifecycleService()
    required = lifecycle.account_confirmation_required(db, membership)
    via = (
        "notify_account_create" if required else "notify_project_create"
    )
    return required, via


def _to_user_project_membership_read(
    db: Session,
    membership: ProjectUser,
) -> UserProjectMembershipRead:
    confirmation_required, confirmation_via = _membership_confirmation_context(
        db, membership
    )
    return UserProjectMembershipRead(
        project_user_id=membership.id,
        project_id=membership.project.id,
        project_name=membership.project.name,
        project_site_project_id=membership.project.site_project_id,
        project_is_active=membership.project.is_active,
        role=membership.role,
        is_project_pi=_role_is_pi(membership.role),
        account_confirmation_required=confirmation_required,
        account_confirmation_via=confirmation_via,
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
        account_is_active=membership.is_active,
        account_state=membership.account_state,
        account_state_updated_at=membership.account_state_updated_at,
        email_sent_at=membership.email_sent_at,
        account_made_at=membership.account_made_at,
        aime_confirmation_sent_at=membership.aime_confirmation_sent_at,
        source_packet_rec_id=membership.source_packet_rec_id,
        source_trans_rec_id=membership.source_trans_rec_id,
        source_transaction_id=membership.source_transaction_id,
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


def _clean_string(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


@router.post("/", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Create a new user."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User with this email already exists")

    user = User(email=payload.email, name=payload.name, tags=_normalize_tags(payload.tags))
    db.add(user)
    db.commit()
    db.refresh(user)
    return _to_user_read(user)


@router.get("/", response_model=list[UserRead])
def list_users(
    include_debug: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[UserRead]:
    """Return all users (people)."""
    rows = (
        db.query(User)
        .options(joinedload(User.project_users).joinedload(ProjectUser.project))
        .order_by(User.created_at.desc())
        .all()
    )
    visible_rows = rows if include_debug else [
        user for user in rows if not _has_debug_tag(user.tags)
    ]
    return [
        _to_user_read(user, include_debug_projects=include_debug)
        for user in visible_rows
    ]


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)) -> UserRead:
    """Return a single user by ID."""
    user = (
        db.query(User)
        .options(joinedload(User.project_users).joinedload(ProjectUser.project))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _to_user_read(user)


@router.get("/{user_id}/packets", response_model=list[EntityPacketRead])
def get_user_packets(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[EntityPacketRead]:
    """Return packets that created or modified a user's values."""
    user = (
        db.query(User)
        .options(joinedload(User.project_users))
        .filter(User.id == user_id)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

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

    # Collect membership source IDs to avoid per-membership queries (N+1 pattern).
    source_packet_rec_ids: set[int] = set()
    source_trans_rec_ids: set[int] = set()
    source_transaction_ids: set[int] = set()

    for membership in user.project_users:
        if membership.source_packet_rec_id is not None:
            source_packet_rec_ids.add(membership.source_packet_rec_id)
        if membership.source_trans_rec_id is not None:
            source_trans_rec_ids.add(membership.source_trans_rec_id)
        if membership.source_transaction_id is not None:
            source_transaction_ids.add(membership.source_transaction_id)

    if source_packet_rec_ids:
        add_packets(
            db.query(AMIEPacket)
            .filter(AMIEPacket.packet_rec_id.in_(source_packet_rec_ids))
            .all(),
            "membership.source_packet_rec_id",
        )
    if source_trans_rec_ids:
        add_packets(
            db.query(AMIEPacket)
            .filter(AMIEPacket.trans_rec_id.in_(source_trans_rec_ids))
            .all(),
            "membership.source_trans_rec_id",
        )
    if source_transaction_ids:
        add_packets(
            db.query(AMIEPacket)
            .filter(AMIEPacket.transaction_id.in_(source_transaction_ids))
            .all(),
            "membership.source_transaction_id",
        )

    if user.person_id:
        add_packets(
            db.query(AMIEPacket)
            .join(AMIENewUserPacket, AMIENewUserPacket.packet_id == AMIEPacket.id)
            .filter(AMIENewUserPacket.user_person_id == user.person_id)
            .all(),
            "new_user.user_person_id",
        )
        add_packets(
            db.query(AMIEPacket)
            .join(AMIELifecyclePacket, AMIELifecyclePacket.packet_id == AMIEPacket.id)
            .filter(
                or_(
                    AMIELifecyclePacket.person_id == user.person_id,
                    AMIELifecyclePacket.keep_person_id == user.person_id,
                    AMIELifecyclePacket.delete_person_id == user.person_id,
                )
            )
            .all(),
            "lifecycle.person_id",
        )
    if user.email:
        add_packets(
            db.query(AMIEPacket)
            .join(AMIENewUserPacket, AMIENewUserPacket.packet_id == AMIEPacket.id)
            .filter(AMIENewUserPacket.user_email == user.email)
            .all(),
            "new_user.user_email",
        )
    if user.global_id:
        add_packets(
            db.query(AMIEPacket)
            .join(AMIENewUserPacket, AMIENewUserPacket.packet_id == AMIEPacket.id)
            .filter(AMIENewUserPacket.user_global_id == user.global_id)
            .all(),
            "new_user.user_global_id",
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


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
) -> UserRead:
    """Update a user's stored details."""
    user = (
        db.query(User)
        .options(joinedload(User.project_users).joinedload(ProjectUser.project))
        .filter(User.id == user_id)
        .first()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return _to_user_read(user)

    if "tags" in updates:
        user.tags = _normalize_tags(updates["tags"])

    if "email" in updates:
        email = _clean_string(updates["email"])
        if email and email != user.email:
            existing = (
                db.query(User)
                .filter(User.email == email, User.id != user.id)
                .first()
            )
            if existing is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Another user already has this email address",
                )
        user.email = email

    string_fields = (
        "name",
        "first_name",
        "middle_name",
        "last_name",
        "person_id",
        "global_id",
        "organization",
        "org_code",
        "department",
        "nsf_status_code",
        "remote_site_login",
        "source_site_name",
    )
    for field in string_fields:
        if field in updates:
            setattr(user, field, _clean_string(updates[field]))

    if "name" in updates and not user.name:
        raise HTTPException(status_code=400, detail="User name cannot be empty")

    if "dn_list" in updates:
        user.dn_list = _normalize_tags(updates["dn_list"])
    if "service_units_allocated" in updates:
        user.service_units_allocated = updates["service_units_allocated"]
    if "is_active" in updates:
        user.is_active = bool(updates["is_active"])

    db.commit()
    db.refresh(user)
    return _to_user_read(user)


@router.get("/{user_id}/memberships", response_model=list[UserProjectMembershipRead])
def get_user_memberships(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[UserProjectMembershipRead]:
    """Return all project memberships for a person."""
    user = db.query(User.id).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    memberships = (
        db.query(ProjectUser)
        .options(joinedload(ProjectUser.project))
        .filter(ProjectUser.user_id == user_id)
        .order_by(ProjectUser.created_at.desc())
        .all()
    )

    return [_to_user_project_membership_read(db, membership) for membership in memberships]


@router.get("/{user_id}/packet-details", response_model=list[UserPacketDetailRead])
def get_user_packet_details(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> list[UserPacketDetailRead]:
    """Return packet-derived details known for a person from incoming packets."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    filters = []
    if user.person_id:
        filters.append(AMIENewUserPacket.user_person_id == user.person_id)
    if user.email:
        filters.append(AMIENewUserPacket.user_email == user.email)
    if user.global_id:
        filters.append(AMIENewUserPacket.user_global_id == user.global_id)

    if not filters:
        return []

    rows = (
        db.query(AMIENewUserPacket, AMIEPacket)
        .join(AMIEPacket, AMIEPacket.id == AMIENewUserPacket.packet_id)
        .filter(or_(*filters))
        .order_by(AMIEPacket.packet_rec_id.desc())
        .limit(500)
        .all()
    )

    return [
        UserPacketDetailRead(
            packet_rec_id=packet.packet_rec_id,
            trans_rec_id=packet.trans_rec_id,
            transaction_id=packet.transaction_id,
            packet_type=packet.packet_type,
            packet_timestamp=packet.packet_timestamp,
            packet_received_at=packet.created_at,
            grant_number=new_user.grant_number,
            project_id=new_user.project_id,
            resource=new_user.resource,
            allocated_resource=new_user.allocated_resource,
            service_units_allocated=new_user.service_units_allocated,
            service_units_remaining=new_user.service_units_remaining,
            user_person_id=new_user.user_person_id,
            user_global_id=new_user.user_global_id,
            user_first_name=new_user.user_first_name,
            user_middle_name=new_user.user_middle_name,
            user_last_name=new_user.user_last_name,
            user_organization=new_user.user_organization,
            user_org_code=new_user.user_org_code,
            user_department=new_user.user_department,
            user_email=new_user.user_email,
            user_business_phone_number=new_user.user_business_phone_number,
            user_remote_site_login=new_user.user_remote_site_login,
            nsf_status_code=new_user.nsf_status_code,
            role_list=new_user.role_list or [],
            user_dn_list=new_user.user_dn_list or [],
            user_requested_login_list=new_user.user_requested_login_list or [],
            site_person_ids=new_user.site_person_ids or [],
            raw_body=new_user.raw_body or {},
        )
        for new_user, packet in rows
    ]


@router.post(
    "/{user_id}/invites",
    response_model=InviteCreateResponse,
    status_code=201,
)
def create_user_invite(
    user_id: uuid.UUID,
    payload: UserInviteCreate,
    db: Session = Depends(get_db),
) -> InviteCreateResponse:
    """Create and send an invite link for a person.

    Invite is person-centric and applies to the person's active memberships.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.email:
        raise HTTPException(status_code=400, detail="User does not have an email address")

    memberships = (
        db.query(ProjectUser)
        .options(joinedload(ProjectUser.project))
        .filter(ProjectUser.user_id == user_id)
        .order_by(ProjectUser.created_at.desc())
        .all()
    )
    if not memberships:
        raise HTTPException(status_code=404, detail="User has no project memberships")

    active_memberships = [membership for membership in memberships if membership.is_active]
    if not active_memberships:
        raise HTTPException(
            status_code=400,
            detail="User has no active project memberships to invite",
        )

    lifecycle = AccountLifecycleService()
    for membership in active_memberships:
        if membership.account_state != ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE:
            lifecycle.mark_email_sent(membership)

    invite_service = InviteService()
    result = invite_service.create_invite(
        db,
        user_id=user.id,
        email=user.email,
        expires_in_hours=payload.expires_in_hours,
        invited_by=payload.invited_by or "system:person-page",
        redirect_path=payload.redirect_path,
        metadata={
            **(payload.metadata or {}),
            "user_id": str(user.id),
            "project_user_ids": [str(membership.id) for membership in active_memberships],
            "project_ids": [str(membership.project_id) for membership in active_memberships],
            "source_packet_rec_ids": [
                membership.source_packet_rec_id for membership in active_memberships
            ],
            "source_trans_rec_ids": [
                membership.source_trans_rec_id for membership in active_memberships
            ],
            "source_transaction_ids": [
                membership.source_transaction_id for membership in active_memberships
            ],
        },
        send_email=payload.send_email,
    )

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
