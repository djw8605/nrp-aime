"""Central API router that aggregates all sub-routers."""

from fastapi import APIRouter

from app.api import audit, demo, packets, projects, users

api_router = APIRouter()

api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(audit.router, prefix="/audit", tags=["audit"])
api_router.include_router(demo.router, prefix="/demo", tags=["demo"])
api_router.include_router(packets.router, prefix="/packets", tags=["packets"])
