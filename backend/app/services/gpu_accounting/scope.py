"""Which projects are GPU-hour allocations reported to ACCESS."""

from __future__ import annotations

from app.config import settings
from app.models.project import Project


def is_gpu_project(project: Project) -> bool:
    """Return True when the project's allocated resource is the GPU resource."""
    resource = (settings.amie_gpu_resource_name or "").strip()
    return bool(resource) and (project.allocated_resource or "").strip() == resource


def is_exportable_gpu_project(project: Project) -> bool:
    """Return True when GPU usage for *project* can be reported to ACCESS."""
    tags = {str(tag).strip().lower() for tag in (project.tags or [])}
    return (
        is_gpu_project(project)
        and bool((project.site_project_id or "").strip())
        and bool((project.kubernetes_namespace or "").strip())
        and "debug" not in tags
    )
