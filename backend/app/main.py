"""FastAPI application entry point."""

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not settings.auth_admin_jwks_url:
    logger.warning(
        "AUTH_ADMIN_JWKS_URL is not configured: OIDC ID token signatures are NOT "
        "verified. Set auth_admin_jwks_url to the provider JWKS endpoint before "
        "deploying to production."
    )

_DEFAULT_SECRET = "dev-change-me"
if settings.app_secret_key == _DEFAULT_SECRET:
    if settings.debug:
        logger.warning(
            "APP_SECRET_KEY is set to the insecure default '%s'. "
            "Set a strong random secret before deploying to production.",
            _DEFAULT_SECRET,
        )
    else:
        logger.error(
            "APP_SECRET_KEY is set to the insecure default '%s' while debug=False. "
            "Set APP_SECRET_KEY to a cryptographically random value and restart.",
            _DEFAULT_SECRET,
        )
        sys.exit(1)

app = FastAPI(
    title=settings.app_name,
    description="API for managing NRP allocations via the AIME/AMIE system.",
    version="0.1.0",
)

# In debug mode allow the default Vite dev server origin; in production restrict
# via ALLOWED_ORIGINS.  Browsers refuse the combination of allow_credentials=True
# and allow_origins=["*"], so we never use a wildcard with credentials.
_cors_origins = (
    ["http://localhost:5173", "http://localhost:3000"]
    if settings.debug
    else settings.allowed_origins
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
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
