"""Central API router that aggregates all sub-routers."""

from fastapi import APIRouter

from app.api import projects, users

api_router = APIRouter()

api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
