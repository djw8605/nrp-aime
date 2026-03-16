"""Alerting service for webhook/slack/email notifications."""

from __future__ import annotations

import logging
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.alert_notification import AlertNotification

logger = logging.getLogger(__name__)


class AlertService:
    """Dispatch and throttle operational alerts."""

    @staticmethod
    def _post_json(url: str, payload: dict[str, Any]) -> None:
        httpx.post(url, json=payload, timeout=10).raise_for_status()

    @staticmethod
    def _parse_recipients(value: str) -> list[str]:
        return [entry.strip() for entry in value.split(",") if entry.strip()]

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
        email_message.set_content(
            "\n".join(
                [
                    f"Alert Key: {alert_key}",
                    f"Category: {category}",
                    f"Severity: {severity}",
                    "",
                    message,
                    "",
                    f"Payload: {payload or {}}",
                ]
            )
        )

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

    @staticmethod
    def _can_send(row: AlertNotification | None) -> bool:
        if row is None or row.last_sent_at is None:
            return True
        min_interval = timedelta(minutes=max(1, settings.alert_min_interval_minutes))
        return datetime.now(UTC) - row.last_sent_at >= min_interval

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
        force: bool = False,
    ) -> dict[str, Any]:
        """Send alert to configured hooks with DB-backed throttling."""
        row = (
            db.query(AlertNotification)
            .filter(AlertNotification.alert_key == alert_key)
            .first()
        )
        if row is None:
            row = AlertNotification(
                alert_key=alert_key,
                category=category,
                severity=severity,
                title=title,
                message=message,
                payload=payload or {},
                send_count=0,
                is_active=True,
            )
            db.add(row)
            db.flush()

        row.category = category
        row.severity = severity
        row.title = title
        row.message = message
        row.payload = payload or {}
        row.is_active = True
        row.resolved_at = None

        if not force and not cls._can_send(row):
            db.commit()
            return {"sent": False, "reason": "throttled"}

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

        row.send_count += 1
        row.last_sent_at = datetime.now(UTC)
        db.commit()
        return {"sent": True, "channels": sent_channels, "errors": errors}

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
        db.commit()
