"""Pydantic schemas for Project."""

import uuid
from datetime import datetime

from pydantic import BaseModel

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
    resource_type: str | None
    cpu_allocated: int
    gpu_allocated: int
    kubernetes_namespace: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ProjectReadWithUsers(ProjectRead):
    """Schema for reading a project along with its users."""

    users: list[UserRead] = []

    model_config = {"from_attributes": True}


class ProjectUsage(BaseModel):
    """Schema for project resource usage."""

    cpu_allocated: int
    cpu_used: float
    gpu_allocated: int
    gpu_used: float
