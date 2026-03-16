"""AMIE Usage API export service."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import isfinite

from amieclient import UsageClient
from amieclient.usage import AdjustmentUsageRecord
from sqlalchemy.orm import Session

from app.config import settings
from app.models.amie_usage_export import AMIEUsageExport
from app.models.project import Project
from app.models.project_usage_snapshot import ProjectUsageSnapshot
from app.schemas.project import ProjectUsage
from app.services.prometheus.service import PrometheusService

logger = logging.getLogger(__name__)


class AMIEUsageService:
    """Builds and exports usage records to AMIE's usage endpoint."""

    def __init__(
        self,
        *,
        site_name: str | None = None,
        api_key: str | None = None,
        usage_url: str | None = None,
    ) -> None:
        self.site_name = site_name or settings.amie_site_name
        self.api_key = api_key or settings.amie_api_key
        self.usage_url = usage_url or settings.amie_usage_url
        self.gpu_charge_factor = Decimal(str(settings.amie_usage_gpu_charge_factor))
        self.default_username = settings.amie_usage_default_username
        self.interval_minutes = max(1, settings.amie_usage_interval_minutes)
        self.prometheus = PrometheusService()

    def _current_interval(self) -> tuple[datetime, datetime]:
        """Return the last completed interval window in UTC."""
        now = datetime.now(tz=UTC)
        interval_seconds = self.interval_minutes * 60
        current_bucket_start_seconds = (
            int(now.timestamp()) // interval_seconds
        ) * interval_seconds
        interval_end = datetime.fromtimestamp(current_bucket_start_seconds, tz=UTC)
        interval_start = interval_end - timedelta(seconds=interval_seconds)
        return interval_start, interval_end

    def _pick_username(self, project: Project) -> str:
        # Prefer an explicit AMIE/remote login from project membership.
        for pu in project.project_users:
            if pu.remote_site_login:
                return pu.remote_site_login
            if pu.user.remote_site_login:
                return pu.user.remote_site_login
        for pu in project.project_users:
            if pu.user.email and "@" in pu.user.email:
                return pu.user.email.split("@", 1)[0]
            if pu.user.person_id:
                return pu.user.person_id
        return self.default_username

    def _compute_charge(self, project_usage) -> Decimal:
        if not isfinite(project_usage.cpu_used) or not isfinite(project_usage.gpu_used):
            return Decimal("0")
        cpu = Decimal(str(project_usage.cpu_used))
        gpu = Decimal(str(project_usage.gpu_used))
        return (cpu + (gpu * self.gpu_charge_factor)).quantize(Decimal("0.000001"))

    @staticmethod
    def _decimal_or_zero(value: float) -> Decimal:
        if not isfinite(value):
            return Decimal("0")
        return Decimal(str(value))

    def _local_record_id(self, project: Project, interval_start: datetime) -> str:
        return f"nrp-usage-{project.id}-{interval_start.strftime('%Y%m%d%H%M')}"

    def _already_exported(self, db: Session, local_record_id: str) -> bool:
        return (
            db.query(AMIEUsageExport)
            .filter(AMIEUsageExport.local_record_id == local_record_id)
            .first()
            is not None
        )

    def _build_record(
        self,
        *,
        project: Project,
        username: str,
        charge: Decimal,
        interval_start: datetime,
        local_record_id: str,
    ) -> AdjustmentUsageRecord:
        return AdjustmentUsageRecord(
            adjustment_type="debit",
            charge=str(charge),
            start_time=interval_start.isoformat(),
            local_project_id=project.site_project_id,
            local_record_id=local_record_id,
            resource=project.resource_type,
            username=username,
            comment=f"NRP periodic usage export for interval starting {interval_start.isoformat()}",
            local_reference=local_record_id,
        )

    def _upsert_usage_snapshot(
        self,
        db: Session,
        *,
        project: Project,
        current_usage: ProjectUsage,
        interval_usage: ProjectUsage,
        interval_charge: Decimal,
    ) -> ProjectUsageSnapshot:
        snapshot = (
            db.query(ProjectUsageSnapshot)
            .filter(ProjectUsageSnapshot.project_id == project.id)
            .first()
        )
        if snapshot is None:
            snapshot = ProjectUsageSnapshot(project_id=project.id)
            db.add(snapshot)

        snapshot.interval_minutes = self.interval_minutes
        snapshot.cpu_used_current = self._decimal_or_zero(current_usage.cpu_used)
        snapshot.gpu_used_current = self._decimal_or_zero(current_usage.gpu_used)
        snapshot.cpu_used_interval = self._decimal_or_zero(interval_usage.cpu_used)
        snapshot.gpu_used_interval = self._decimal_or_zero(interval_usage.gpu_used)
        snapshot.charge_interval = interval_charge
        snapshot.last_collected_at = datetime.now(UTC)
        return snapshot

    def send_project_usage(
        self,
        db: Session,
        *,
        project: Project,
        interval_start: datetime,
        interval_end: datetime,
        enable_send: bool,
    ) -> str:
        """Send one usage adjustment record for a project."""
        current_usage = self.prometheus.get_usage(project)
        interval_usage = self.prometheus.get_interval_usage(
            project, self.interval_minutes, interval_end=interval_end
        )
        charge = self._compute_charge(interval_usage)

        snapshot = self._upsert_usage_snapshot(
            db,
            project=project,
            current_usage=current_usage,
            interval_usage=interval_usage,
            interval_charge=charge,
        )
        # Persist usage snapshots even if AMIE export is disabled or fails.
        db.commit()

        if not enable_send:
            logger.debug(
                "Collected usage snapshot for project %s (API key missing; export disabled)",
                project.id,
            )
            return "updated_only"

        if not project.site_project_id:
            logger.debug("Skipping project %s: no site_project_id", project.id)
            return "skipped"
        if not project.resource_type:
            logger.debug("Skipping project %s: no resource_type", project.id)
            return "skipped"

        local_record_id = self._local_record_id(project, interval_start)
        if self._already_exported(db, local_record_id):
            logger.debug("Skipping project %s: usage record already exported", project.id)
            return "skipped"
        if charge <= Decimal("0"):
            logger.debug("Skipping project %s: computed charge is zero", project.id)
            return "skipped"

        username = self._pick_username(project)
        record = self._build_record(
            project=project,
            username=username,
            charge=charge,
            interval_start=interval_start,
            local_record_id=local_record_id,
        )

        logger.debug(
            "Sending AMIE usage record local_record_id=%s project_id=%s resource=%s project_code=%s charge=%s username=%s",
            local_record_id,
            project.id,
            project.resource_type,
            project.site_project_id,
            str(charge),
            username,
        )

        with UsageClient(
            site_name=self.site_name, api_key=self.api_key, usage_url=self.usage_url
        ) as usage_client:
            responses = usage_client.send(record)

        validation_failed = any(r.failed_records for r in responses)
        snapshot.last_sent_at = datetime.now(UTC)
        if not validation_failed:
            snapshot.total_charge_sent = (
                (snapshot.total_charge_sent or Decimal("0")) + charge
            ).quantize(Decimal("0.000001"))

        export_row = AMIEUsageExport(
            project_id=project.id,
            local_record_id=local_record_id,
            usage_type="adjustment",
            adjustment_type="debit",
            interval_start=interval_start,
            interval_end=interval_end,
            charge=charge,
            resource=project.resource_type,
            username=username,
            status="failed" if validation_failed else "sent",
            response_payload={
                "responses": [
                    {
                        "message": r.message,
                        "failed_records": [fr.as_dict() for fr in r.failed_records],
                    }
                    for r in responses
                ]
            },
        )
        db.add(export_row)
        db.commit()
        return "failed" if validation_failed else "sent"

    def send_all_projects_usage(self, db: Session) -> dict[str, int]:
        """Collect usage snapshots and send interval deltas to AMIE when enabled."""
        enable_send = bool(self.api_key)
        if not enable_send:
            logger.warning(
                "AMIE_API_KEY is not configured; collecting usage snapshots without export."
            )

        interval_start, interval_end = self._current_interval()
        updated = 0
        sent = 0
        failed = 0
        skipped = 0

        projects = db.query(Project).all()
        for project in projects:
            try:
                result = self.send_project_usage(
                    db,
                    project=project,
                    interval_start=interval_start,
                    interval_end=interval_end,
                    enable_send=enable_send,
                )
                updated += 1
                if result == "sent":
                    sent += 1
                elif result == "failed":
                    failed += 1
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001
                failed += 1
                db.rollback()
                logger.exception(
                    "Failed sending AMIE usage for project %s", project.id
                )

        logger.info(
            "AMIE usage export cycle complete interval_start=%s updated=%s sent=%s failed=%s skipped=%s",
            interval_start.isoformat(),
            updated,
            sent,
            failed,
            skipped,
        )
        return {"updated": updated, "sent": sent, "failed": failed, "skipped": skipped}
