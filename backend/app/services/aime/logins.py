"""AMIE login helpers."""

from __future__ import annotations

AMIE_LOGIN_MAX_LENGTH = 30


def amie_login(login: str | None) -> str | None:
    """The login as AMIE stores it: CILogon subject URLs exceed AMIE's
    varchar(30) username, so keep the last 30 characters (the unique id)."""
    cleaned = (login or "").strip()
    if not cleaned:
        return None
    return cleaned[-AMIE_LOGIN_MAX_LENGTH:]
