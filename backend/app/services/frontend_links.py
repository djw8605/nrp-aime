"""Absolute links into the admin frontend, for alerts and emails."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from app.config import settings


def frontend_url(path: str, **query: Any) -> str:
    """Return ``path`` joined to ``FRONTEND_BASE_URL`` (relative if unset)."""
    base = str(settings.frontend_base_url or "").rstrip("/")
    params = {key: value for key, value in query.items() if value not in (None, "")}
    if params:
        path = f"{path}?{urlencode(params)}"
    return f"{base}{path}" if base else path


def project_url(project_id: Any) -> str:
    return frontend_url(f"/projects/{project_id}")


def person_url(user_id: Any) -> str:
    return frontend_url(f"/people/{user_id}")


def transaction_url(transaction_id: Any) -> str:
    return frontend_url(f"/transactions/{transaction_id}")


def packet_logs_url(*, q: Any = None) -> str:
    return frontend_url("/packets/logs", q=q)
