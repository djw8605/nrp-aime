"""Security helpers for invite token and state handling."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from app.config import settings


def generate_secure_token() -> str:
    """Return URL-safe random token for invite links."""
    return secrets.token_urlsafe(32)


def hash_invite_token(token: str) -> str:
    """Hash invite token with app secret pepper (raw token is never stored)."""
    payload = f"{settings.app_secret_key}:{token}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def mask_email(email: str) -> str:
    """Mask email for safe invite previews."""
    text = (email or "").strip()
    if "@" not in text:
        return "***"
    local, domain = text.split("@", 1)
    if len(local) <= 1:
        local_mask = "*"
    elif len(local) == 2:
        local_mask = f"{local[0]}*"
    else:
        local_mask = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{local_mask}@{domain}"


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def sign_state(payload: dict[str, Any]) -> str:
    """Sign state payload for auth redirect round trip."""
    envelope = {
        "payload": payload,
        "ts": int(time.time()),
    }
    encoded = _b64url_encode(json.dumps(envelope, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.app_secret_key.encode("utf-8"),
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded}.{signature}"


def verify_state(state: str, *, max_age_seconds: int) -> dict[str, Any]:
    """Verify signed state integrity and expiration window."""
    if "." not in state:
        raise ValueError("Invalid state format")
    encoded, signature = state.split(".", 1)
    expected = hmac.new(
        settings.app_secret_key.encode("utf-8"),
        encoded.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid state signature")

    try:
        envelope = json.loads(_b64url_decode(encoded))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid state payload") from exc

    ts = int(envelope.get("ts", 0))
    if ts <= 0:
        raise ValueError("State timestamp missing")
    age = int(time.time()) - ts
    if age > max_age_seconds:
        raise ValueError("State expired")
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("State payload missing")
    return payload
