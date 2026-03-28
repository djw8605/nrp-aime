"""Pydantic schemas for Project."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserRead


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    aime_allocation_id: str
    name: str
    tags: list[str] = Field(default_factory=list)
    resource_type: str | None = None
    cpu_allocated: int = 0
    gpu_allocated: int = 0
    kubernetes_namespace: str | None = None


class ProjectRead(BaseModel):
    """Schema for reading a project."""

    id: uuid.UUID
    aime_allocation_id: str
    name: str
    grant_number: str | None = None
    allocation_record_id: str | None = None
    site_project_id: str | None = None
    allocation_type: str | None = None
    request_type: str | None = None
    source_packet_rec_id: int | None = None
    source_trans_rec_id: int | None = None
    source_transaction_id: int | None = None
    source_site_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    allocated_resource: str | None = None
    service_units_allocated: float | None = None
    service_units_remaining: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    project_title: str | None = None
    pfos_number: str | None = None
    board_type: str | None = None
    pi_person_id: str | None = None
    pi_first_name: str | None = None
    pi_middle_name: str | None = None
    pi_last_name: str | None = None
    pi_email: str | None = None
    pi_organization: str | None = None
    pi_org_code: str | None = None
    pi_department: str | None = None
    pi_business_phone_number: str | None = None
    resource_type: str | None
    cpu_allocated: int
    gpu_allocated: int
    cpu_used_current: float | None = None
    gpu_used_current: float | None = None
    usage_source: str | None = None
    usage_last_collected_at: datetime | None = None
    is_active: bool
    kubernetes_namespace: str | None
    authentik_group_name: str | None = None
    lifecycle_state: str
    provisioning_state: str
    provisioning_requested_at: datetime | None = None
    provisioning_started_at: datetime | None = None
    provisioning_completed_at: datetime | None = None
    provisioning_last_error: str | None = None
    provisioning_alerted_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectUpdate(BaseModel):
    """Schema for updating a project."""

    aime_allocation_id: str | None = None
    name: str | None = None
    grant_number: str | None = None
    allocation_record_id: str | None = None
    site_project_id: str | None = None
    allocation_type: str | None = None
    request_type: str | None = None
    source_packet_rec_id: int | None = None
    source_trans_rec_id: int | None = None
    source_transaction_id: int | None = None
    source_site_name: str | None = None
    tags: list[str] | None = None
    allocated_resource: str | None = None
    service_units_allocated: float | None = None
    service_units_remaining: float | None = None
    start_date: date | None = None
    end_date: date | None = None
    project_title: str | None = None
    pfos_number: str | None = None
    board_type: str | None = None
    pi_person_id: str | None = None
    pi_first_name: str | None = None
    pi_middle_name: str | None = None
    pi_last_name: str | None = None
    pi_email: str | None = None
    pi_organization: str | None = None
    pi_org_code: str | None = None
    pi_department: str | None = None
    pi_business_phone_number: str | None = None
    resource_type: str | None = None
    cpu_allocated: int | None = None
    gpu_allocated: int | None = None
    kubernetes_namespace: str | None = None
    authentik_group_name: str | None = None
    lifecycle_state: str | None = None
    provisioning_state: str | None = None
    provisioning_requested_at: datetime | None = None
    provisioning_started_at: datetime | None = None
    provisioning_completed_at: datetime | None = None
    provisioning_last_error: str | None = None
    provisioning_alerted_at: datetime | None = None
    is_active: bool | None = None


class ProjectReadWithUsers(ProjectRead):
    """Schema for reading a project along with its users."""

    users: list[UserRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ProjectUsage(BaseModel):
    """Schema for project resource usage."""

    cpu_allocated: int
    cpu_used: float
    gpu_allocated: int
    gpu_used: float
    usage_source: str | None = None
    usage_last_collected_at: datetime | None = None
    usage_note: str | None = None


class ProjectSummary(BaseModel):
    """Schema for top-level project and usage KPIs."""

    total_projects: int
    active_projects: int
    total_users: int
    active_users: int
    total_cpu_allocated: int
    total_gpu_allocated: int
    total_cpu_used: float
    total_gpu_used: float
    projects_with_service_units: int = 0
    total_service_units_allocated: float = 0.0
