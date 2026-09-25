"""Alerting service for webhook/slack/email notifications."""

from __future__ import annotations

from html import escape
import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.alert_notification import AlertNotification
from app.services.database_health import is_database_write_unavailable

logger = logging.getLogger(__name__)


class AlertService:
    """Dispatch and throttle operational alerts."""

    # alert_key -> last send time in this process; backs up the DB throttle.
    _process_last_sent: dict[str, datetime] = {}

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any]) -> None:
        httpx.post(url, json=payload, timeout=10).raise_for_status()

    @staticmethod
    def _parse_recipients(value: str) -> list[str]:
        return [entry.strip() for entry in value.split(",") if entry.strip()]

    @staticmethod
    def _render_html_value(value: Any) -> str:
        text = str(value)
        escaped_text = escape(text, quote=True).replace("\n", "<br>")
        if isinstance(value, str):
            url = value.strip()
            if url.startswith(("http://", "https://")):
                escaped_url = escape(url, quote=True)
                return (
                    f'<a href="{escaped_url}" '
                    'style="color:#2563eb;text-decoration:underline;">'
                    f"{escaped_text}</a>"
                )
        return escaped_text

    @staticmethod
    def _build_html_email(
        *,
        alert_key: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> str:
        """Build a styled HTML email body for an alert."""
        severity_colors: dict[str, tuple[str, str]] = {
            "error": ("#dc2626", "#fef2f2"),
            "warn": ("#d97706", "#fffbeb"),
            "warning": ("#d97706", "#fffbeb"),
            "info": ("#2563eb", "#eff6ff"),
        }
        header_color, _bg_color = severity_colors.get(
            severity.lower(), ("#6b7280", "#f9fafb")
        )

        detail_rows = ""
        if payload:
            for key, value in payload.items():
                if value is not None and value != "":
                    label = escape(key.replace("_", " ").title(), quote=True)
                    rendered_value = AlertService._render_html_value(value)
                    detail_rows += (
                        f"<tr>"
                        f'<td style="padding:8px 12px;font-weight:600;color:#374151;'
                        f'width:38%;border-bottom:1px solid #f3f4f6;vertical-align:top;">{label}</td>'
                        f'<td style="padding:8px 12px;color:#111827;'
                        f'border-bottom:1px solid #f3f4f6;word-break:break-word;">'
                        f"{rendered_value}</td>"
                        f"</tr>"
                    )

        details_section = ""
        if detail_rows:
            details_section = (
                '<div style="margin-top:24px;">'
                '<p style="margin:0 0 8px;font-size:11px;font-weight:700;'
                "text-transform:uppercase;letter-spacing:0.06em;color:#9ca3af;"
                '">Details</p>'
                '<table style="width:100%;border-collapse:collapse;'
                'background:#f9fafb;border-radius:6px;overflow:hidden;">'
                f"{detail_rows}"
                "</table>"
                "</div>"
            )

        severity_text = escape(severity.upper(), quote=True)
        category_text = escape(category, quote=True)
        title_text = escape(title, quote=True)
        message_text = escape(message, quote=True).replace("\n", "<br>")
        alert_key_text = escape(alert_key, quote=True)

        return (
            "<!DOCTYPE html>"
            '<html lang="en">'
            "<head>"
            '<meta charset="UTF-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1.0">'
            "</head>"
            '<body style="margin:0;padding:24px;background-color:#f3f4f6;'
            "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,"
            'Helvetica,Arial,sans-serif;">'
            '<div style="max-width:600px;margin:0 auto;">'
            f'<div style="background:{header_color};border-radius:8px 8px 0 0;padding:24px 28px;">'
            f'<p style="margin:0 0 6px;font-size:11px;font-weight:700;'
            f"text-transform:uppercase;letter-spacing:0.1em;"
            f'color:rgba(255,255,255,0.75);">'
            f"{severity_text} &bull; {category_text}"
            f"</p>"
            f'<h1 style="margin:0;font-size:22px;font-weight:700;color:#ffffff;'
            f'line-height:1.3;">{title_text}</h1>'
            f"</div>"
            '<div style="background:#ffffff;padding:24px 28px;'
            'border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;">'
            f'<p style="margin:0;font-size:15px;color:#374151;line-height:1.7;">'
            f"{message_text}</p>"
            f"{details_section}"
            "</div>"
            '<div style="background:#f9fafb;border:1px solid #e5e7eb;border-top:none;'
            'border-radius:0 0 8px 8px;padding:12px 28px;">'
            '<p style="margin:0;font-size:12px;color:#9ca3af;">'
            f"Alert Key:&nbsp;"
            f'<code style="background:#e5e7eb;padding:2px 6px;border-radius:3px;'
            f'font-size:11px;color:#374151;">{alert_key_text}</code>'
            "</p>"
            "</div>"
            "</div>"
            "</body>"
            "</html>"
        )

    @classmethod
    def _send_email_alert(
        cls,
        *,
        alert_key: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        recipients = cls._parse_recipients(settings.alert_email_to)
        sender = settings.alert_email_from.strip()
        host = settings.alert_smtp_host.strip()
        if not recipients or not sender or not host:
            return False

        email_message = EmailMessage()
        email_message["Subject"] = f"[{severity.upper()}] {title}"
        email_message["From"] = sender
        email_message["To"] = ", ".join(recipients)

        plain_lines = [
            f"Alert Key: {alert_key}",
            f"Category: {category}",
            f"Severity: {severity}",
            "",
            message,
        ]
        if payload:
            plain_lines += ["", "Details:"]
            plain_lines += [
                f"  {k}: {v}" for k, v in payload.items() if v is not None and v != ""
            ]
        email_message.set_content("\n".join(plain_lines))

        html_body = cls._build_html_email(
            alert_key=alert_key,
            category=category,
            severity=severity,
            title=title,
            message=message,
            payload=payload,
        )
        email_message.add_alternative(html_body, subtype="html")

        smtp_cls: type[smtplib.SMTP] = smtplib.SMTP
        with smtp_cls(host, settings.alert_smtp_port, timeout=10) as smtp:
            if settings.alert_smtp_use_tls:
                smtp.starttls()
            if settings.alert_smtp_username:
                smtp.login(
                    settings.alert_smtp_username,
                    settings.alert_smtp_password,
                )
            smtp.send_message(email_message)
        return True

    @classmethod
    def _can_send(
        cls, row: AlertNotification | None, alert_key: str, now: datetime
    ) -> bool:
        # The in-process record keeps throttling working when the DB row
        # cannot be written (e.g. Postgres demoted to a read-only standby).
        candidates = [cls._process_last_sent.get(alert_key)]
        if row is not None:
            candidates.append(row.last_sent_at)
        sent_times = [
            ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            for ts in candidates
            if ts is not None
        ]
        if not sent_times:
            return True
        min_interval = timedelta(minutes=max(1, settings.alert_min_interval_minutes))
        return now - max(sent_times) >= min_interval

    @staticmethod
    def _commit_alert_state(db: Session, *, alert_key: str) -> bool:
        """Commit alert bookkeeping; return False if the DB is not writable."""
        try:
            db.commit()
        except SQLAlchemyError as exc:
            if not is_database_write_unavailable(exc):
                raise
            db.rollback()
            logger.error(
                "Could not persist alert state for %s (database not writable): %s",
                alert_key,
                exc,
            )
            return False
        return True

    @classmethod
    def send(
        cls,
        db: Session,
        *,
        alert_key: str,
        category: str,
        severity: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
        email_enabled: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        """Send alert to configured hooks with DB-backed throttling."""
        now = datetime.now(UTC)
        row = (
            db.query(AlertNotification)
            .filter(AlertNotification.alert_key == alert_key)
            .first()
        )
        throttled = not force and not cls._can_send(row, alert_key, now)
        if row is None:
            if throttled:
                return {"sent": False, "reason": "throttled"}
            row = AlertNotification(alert_key=alert_key, send_count=0)
            db.add(row)

        row.category = category
        row.severity = severity
        row.title = title
        row.message = message
        row.payload = payload or {}
        row.is_active = True
        row.resolved_at = None

        if throttled:
            cls._commit_alert_state(db, alert_key=alert_key)
            return {"sent": False, "reason": "throttled"}

        # Record the send before dispatching, so a failed write can never
        # disable throttling and turn every evaluation into a new email.
        row.send_count = (row.send_count or 0) + 1
        row.last_sent_at = now
        persisted = cls._commit_alert_state(db, alert_key=alert_key)
        cls._process_last_sent[alert_key] = now

        alert_payload = {
            "alert_key": alert_key,
            "category": category,
            "severity": severity,
            "title": title,
            "message": message,
            "payload": payload or {},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        sent_channels: list[str] = []
        errors: list[str] = []

        if settings.alert_webhook_url:
            try:
                cls._post_json(settings.alert_webhook_url, alert_payload)
                sent_channels.append("webhook")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"webhook:{exc}")
                logger.exception("Failed to send webhook alert")

        if settings.alert_slack_webhook_url:
            slack_payload = {
                "text": f"[{severity.upper()}] {title}\n{message}\n`{alert_key}`"
            }
            try:
                cls._post_json(settings.alert_slack_webhook_url, slack_payload)
                sent_channels.append("slack")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"slack:{exc}")
                logger.exception("Failed to send slack alert")

        if email_enabled:
            try:
                if cls._send_email_alert(
                    alert_key=alert_key,
                    category=category,
                    severity=severity,
                    title=title,
                    message=message,
                    payload=payload,
                ):
                    sent_channels.append("email")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"email:{exc}")
                logger.exception("Failed to send email alert")

        if not sent_channels:
            logger.warning(
                "ALERT(%s/%s): %s - %s payload=%s",
                category,
                severity,
                title,
                message,
                payload,
            )
            sent_channels.append("log")

        return {
            "sent": True,
            "channels": sent_channels,
            "errors": errors,
            "persisted": persisted,
        }

    @staticmethod
    def resolve(db: Session, *, alert_key: str) -> None:
        """Mark alert key as resolved."""
        row = (
            db.query(AlertNotification)
            .filter(AlertNotification.alert_key == alert_key)
            .first()
        )
        if row is None:
            return
        row.is_active = False
        row.resolved_at = datetime.now(UTC)
        AlertService._commit_alert_state(db, alert_key=alert_key)
