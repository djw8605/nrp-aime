"""Email sending and rendering helpers."""

from __future__ import annotations

import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "templates" / "project_invite_email.txt"
)


class EmailService:
    """Email integration service."""

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

    @staticmethod
    def _parse_subject_and_body(rendered: str) -> tuple[str, str]:
        """Split a rendered template into (subject, body).

        The template's first line must be ``Subject: <value>``.  Everything
        after the following blank line is treated as the body.
        """
        lines = rendered.splitlines()
        subject = "NRP Account Invite"
        body_start = 0
        if lines and lines[0].lower().startswith("subject:"):
            subject = lines[0].split(":", 1)[1].strip()
            # Skip the blank separator line that follows the Subject header.
            body_start = 2 if len(lines) > 1 else 1
        body = "\n".join(lines[body_start:])
        return subject, body

    def send_project_invite_email(
        self,
        *,
        to_email: str,
        project_name: str | None,
        project_names: list[str] | None = None,
        invite_url: str,
        expires_at: datetime,
    ) -> None:
        """Send invite email via SMTP."""
        rendered = self.render_project_invite_email(
            project_name=project_name,
            project_names=project_names,
            invite_url=invite_url,
            expires_at=expires_at,
        )
        subject, body = self._parse_subject_and_body(rendered)

        sender = (settings.invite_email_from or settings.alert_email_from).strip()
        host = settings.alert_smtp_host.strip()

        if not sender or not host:
            logger.warning(
                "invite email not sent to %s: SMTP not configured "
                "(set INVITE_EMAIL_FROM and ALERT_SMTP_HOST)",
                to_email,
            )
            return

        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = to_email
        msg.set_content(body)

        try:
            with smtplib.SMTP(host, settings.alert_smtp_port, timeout=10) as smtp:
                if settings.alert_smtp_use_tls:
                    smtp.starttls()
                if settings.alert_smtp_username:
                    smtp.login(
                        settings.alert_smtp_username,
                        settings.alert_smtp_password,
                    )
                smtp.send_message(msg)
            logger.info("invite email sent to %s", to_email)
        except Exception:
            logger.exception("failed to send invite email to %s", to_email)
            raise
