"""Pydantic schemas for User."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    email: EmailStr
    name: str


class UserRead(BaseModel):
    """Schema for reading a user."""

    id: uuid.UUID
    email: str | None
    name: str
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    person_id: str | None = None
    global_id: str | None = None
    organization: str | None = None
    org_code: str | None = None
    department: str | None = None
    nsf_status_code: str | None = None
    dn_list: list[str] = Field(default_factory=list)
    remote_site_login: str | None = None
    is_active: bool
    project_count: int = 0
    project_names: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectMemberRead(BaseModel):
    """Schema for reading project membership plus user status."""

    id: uuid.UUID
    email: str | None
    name: str
    first_name: str | None = None
    middle_name: str | None = None
    last_name: str | None = None
    person_id: str | None = None
    organization: str | None = None
    department: str | None = None
    nsf_status_code: str | None = None
    dn_list: list[str] = Field(default_factory=list)
    user_is_active: bool
    account_is_active: bool
    account_state: str
    account_state_updated_at: datetime
    email_sent_at: datetime | None = None
    account_made_at: datetime | None = None
    aime_confirmation_sent_at: datetime | None = None
    source_packet_rec_id: int | None = None
    source_trans_rec_id: int | None = None
    source_transaction_id: int | None = None
    role: str | None = None
    resource: str | None = None
    account_remote_site_login: str | None = None
    created_at: datetime


class UserProjectMembershipRead(BaseModel):
    """Schema for one person's membership in one project."""

    project_user_id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    project_site_project_id: str | None = None
    project_is_active: bool
    role: str | None = None
    resource: str | None = None
    account_remote_site_login: str | None = None
    account_is_active: bool
    account_state: str
    account_state_updated_at: datetime
    email_sent_at: datetime | None = None
    account_made_at: datetime | None = None
    aime_confirmation_sent_at: datetime | None = None
    source_packet_rec_id: int | None = None
    source_trans_rec_id: int | None = None
    source_transaction_id: int | None = None


class UserPacketDetailRead(BaseModel):
    """Schema for packet-derived details associated with a person."""

    packet_rec_id: int
    trans_rec_id: int | None = None
    transaction_id: int | None = None
    packet_type: str
    packet_timestamp: datetime | None = None
    packet_received_at: datetime
    grant_number: str
    project_id: str | None = None
    resource: str | None = None
    user_person_id: str | None = None
    user_global_id: str | None = None
    user_first_name: str
    user_middle_name: str | None = None
    user_last_name: str
    user_organization: str
    user_org_code: str
    user_department: str | None = None
    user_email: str | None = None
    user_business_phone_number: str | None = None
    user_remote_site_login: str | None = None
    nsf_status_code: str | None = None
    role_list: list[str] = Field(default_factory=list)
    user_dn_list: list[str] = Field(default_factory=list)
    user_requested_login_list: list[str] = Field(default_factory=list)
    site_person_ids: list[dict[str, Any]] = Field(default_factory=list)
    raw_body: dict[str, Any] = Field(default_factory=dict)


class UserInviteCreate(BaseModel):
    """Payload for sending a person-centric invite."""

    expires_in_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    invited_by: str | None = None
    redirect_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    send_email: bool = True
