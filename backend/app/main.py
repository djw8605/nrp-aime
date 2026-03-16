"""FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.config import settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title=settings.app_name,
    description="API for managing NRP allocations via the AIME/AMIE system.",
    version="0.1.0",
)

# In debug mode allow all origins; in production restrict via ALLOWED_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.app_secret_key,
    session_cookie=settings.auth_session_cookie_name,
    max_age=max(60, settings.auth_session_ttl_minutes * 60),
    same_site="lax",
    https_only=settings.auth_session_https_only,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/healthz")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
