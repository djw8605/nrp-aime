"""Pydantic schemas for User."""

import uuid
from datetime import datetime

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
