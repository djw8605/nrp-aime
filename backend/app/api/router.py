"""Central API router that aggregates all sub-routers."""

from fastapi import APIRouter, Depends

from app.api import audit, auth, demo, invites, ops, packets, projects, users
from app.auth import require_portal_auth

api_router = APIRouter()

protected = [Depends(require_portal_auth)]

api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(
    projects.router,
    prefix="/projects",
    tags=["projects"],
    dependencies=protected,
)
api_router.include_router(
    users.router,
    prefix="/users",
    tags=["users"],
    dependencies=protected,
)
api_router.include_router(
    audit.router,
    prefix="/audit",
    tags=["audit"],
    dependencies=protected,
)
api_router.include_router(
    demo.router,
    prefix="/demo",
    tags=["demo"],
    dependencies=protected,
)
api_router.include_router(
    packets.router,
    prefix="/packets",
    tags=["packets"],
    dependencies=protected,
)
api_router.include_router(
    ops.router,
    prefix="/ops",
    tags=["ops"],
    dependencies=protected,
)
api_router.include_router(invites.router, tags=["invites"])
