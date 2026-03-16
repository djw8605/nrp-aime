"""Email sending and rendering helpers."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / "project_invite_email.txt"
)


class EmailService:
    """Email integration service.

    Current implementation is a stub that logs rendered content.
    """

    def __init__(self) -> None:
        self._template = _TEMPLATE_PATH.read_text(encoding="utf-8")

    def render_project_invite_email(
        self,
        *,
        project_name: str | None,
        project_names: list[str] | None,
        invite_url: str,
        expires_at: datetime,
    ) -> str:
        """Render invite email body from template."""
        if project_names:
            summary = (
                "This invite will activate your access for the following projects: "
                + ", ".join(project_names)
                + "."
            )
        elif project_name:
            summary = f'This invite will activate your access for the project "{project_name}".'
        else:
            summary = "This invite will activate your account access in the NRP portal."

        return self._template.format(
            project_name=project_name or "NRP",
            project_summary=summary,
            invite_url=invite_url,
            expires_at=expires_at.isoformat(),
        )

    def send_project_invite_email(
        self,
        *,
        to_email: str,
        project_name: str | None,
        project_names: list[str] | None = None,
        invite_url: str,
        expires_at: datetime,
    ) -> None:
        """Send invite email (stub)."""
        body = self.render_project_invite_email(
            project_name=project_name,
            project_names=project_names,
            invite_url=invite_url,
            expires_at=expires_at,
        )
        logger.info("STUB(email): sending project invite email to=%s", to_email)
        logger.debug("STUB(email) body for %s:\n%s", to_email, body)
