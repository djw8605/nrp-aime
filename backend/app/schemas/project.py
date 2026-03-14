"""Pydantic schemas for Project."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.user import UserRead


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    aime_allocation_id: str
    name: str
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
    site_project_id: str | None = None
    allocation_type: str | None = None
    request_type: str | None = None
    source_packet_rec_id: int | None = None
    source_trans_rec_id: int | None = None
    source_transaction_id: int | None = None
    resource_type: str | None
    cpu_allocated: int
    gpu_allocated: int
    is_active: bool
    kubernetes_namespace: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


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


class ProjectSummary(BaseModel):
    """Schema for top-level project and usage KPIs."""

    total_projects: int
    active_projects: int
    total_users: int
    active_users: int
    total_cpu_used: float
    total_gpu_used: float
