"""User (person) API endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.amie_packet import AMIEPacket
from app.models.project_user import ProjectUser
from app.models.user import User
from app.schemas.invite import InviteCreateResponse
from app.schemas.user import (
    UserCreate,
    UserInviteCreate,
    UserPacketDetailRead,
    UserProjectMembershipRead,
    UserRead,
)
from app.services.account_lifecycle import AccountLifecycleService
from app.services.invites.service import InviteService

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """Create a new user."""
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="User with this email already exists")

    user = User(email=payload.email, name=payload.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.get("/", response_model=list[UserRead])
def list_users(db: Session = Depends(get_db)) -> list[UserRead]:
    """Return all users (people)."""
    rows = (
        db.query(User)
        .options(joinedload(User.project_users).joinedload(ProjectUser.project))
        .order_by(User.created_at.desc())
        .all()
    )
    results: list[UserRead] = []
    for user in rows:
        project_names = sorted(
            {
                pu.project.name
                for pu in user.project_users
                if pu.project is not None and pu.project.name
            }
        )
        results.append(
            UserRead(
                id=user.id,
                email=user.email,
                name=user.name,
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
                created_at=user.created_at,
            )
        )
    return results


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

    project_names = sorted(
        {
            pu.project.name
            for pu in user.project_users
            if pu.project is not None and pu.project.name
        }
    )
    return UserRead(
        id=user.id,
        email=user.email,
        name=user.name,
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
        created_at=user.created_at,
    )


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

    return [
        UserProjectMembershipRead(
            project_user_id=membership.id,
            project_id=membership.project.id,
            project_name=membership.project.name,
            project_site_project_id=membership.project.site_project_id,
            project_is_active=membership.project.is_active,
            role=membership.role,
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
        for membership in memberships
    ]


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
