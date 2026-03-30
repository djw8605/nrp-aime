"""AMIE Usage API export service.

Usage data is sourced from ClickHouse (``cluster_namespace_usage_daily``).
One AMIE adjustment-debit record is sent per user × namespace × calendar day,
identified by the user's CILogon subject ID (``created_by`` in ClickHouse,
stored as ``User.remote_site_login`` in the NRP database).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from amieclient import UsageClient
from amieclient.usage import AdjustmentUsageRecord
from sqlalchemy.orm import Session

from app.config import settings
from app.models.amie_usage_export import AMIEUsageExport
from app.models.project import Project
from app.models.project_usage_snapshot import ProjectUsageSnapshot
from app.models.user import User
from app.services.clickhouse.service import ClickHouseUsageService, GpuUsageRow

logger = logging.getLogger(__name__)


class AMIEUsageService:
    """Collects GPU usage from ClickHouse and exports records to AMIE."""

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
        self.clickhouse = ClickHouseUsageService()

    # ------------------------------------------------------------------
    # Interval helpers
    # ------------------------------------------------------------------

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

    def _date_range(
        self, interval_start: datetime, interval_end: datetime
    ) -> tuple[date, date]:
        """Convert an interval window to an inclusive ClickHouse date range.

        ``interval_end`` is typically midnight UTC (time == 00:00:00), in which
        case the last full day of data ends at ``interval_end − 1 second``.
        """
        date_from = interval_start.date()
        date_to = (interval_end - timedelta(seconds=1)).date()
        return date_from, date_to

    # ------------------------------------------------------------------
    # Username resolution
    # ------------------------------------------------------------------

    def _pick_username(self, user: User, project: Project) -> str:
        """Return the best available AMIE username for a user in a project.

        Priority:
        1. ``ProjectUser.remote_site_login`` — the HPC/site login registered
           with AMIE for this membership.
        2. ``user.person_id`` — AMIE person identifier.
        3. Local part of ``user.email``.
        4. Configured default username.
        """
        for pu in user.project_users:
            if pu.project_id == project.id and pu.remote_site_login:
                return pu.remote_site_login
        if user.person_id:
            return user.person_id
        if user.email and "@" in user.email:
            return user.email.split("@", 1)[0]
        return self.default_username

    # ------------------------------------------------------------------
    # Record ID
    # ------------------------------------------------------------------

    @staticmethod
    def _local_record_id(project: Project, cilogon_id: str, usage_date: date) -> str:
        """Generate a stable, unique local record ID for one user-day export.

        The CILogon ID may be a long URL so it is hashed to 12 hex chars.
        """
        cilogon_hash = hashlib.sha256(cilogon_id.encode()).hexdigest()[:12]
        date_str = usage_date.strftime("%Y%m%d")
        return f"nrp-gpu-{project.id}-{date_str}-{cilogon_hash}"

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def _already_exported(self, db: Session, local_record_id: str) -> bool:
        return (
            db.query(AMIEUsageExport)
            .filter(AMIEUsageExport.local_record_id == local_record_id)
            .first()
            is not None
        )

    # ------------------------------------------------------------------
    # Snapshot management
    # ------------------------------------------------------------------

    def _upsert_usage_snapshot(
        self,
        db: Session,
        *,
        project: Project,
        gpu_hours_interval: Decimal,
        interval_charge: Decimal,
        sent_charge: Decimal,
        now: datetime,
        mark_sent: bool,
    ) -> None:
        """Create or update the ``ProjectUsageSnapshot`` for *project*."""
        snapshot = (
            db.query(ProjectUsageSnapshot)
            .filter(ProjectUsageSnapshot.project_id == project.id)
            .first()
        )
        if snapshot is None:
            snapshot = ProjectUsageSnapshot(project_id=project.id)
            db.add(snapshot)

        snapshot.interval_minutes = self.interval_minutes
        # CPU is not tracked through ClickHouse.
        snapshot.cpu_used_current = Decimal("0")
        snapshot.cpu_used_interval = Decimal("0")
        # GPU hours for the interval are surfaced as both current and interval.
        snapshot.gpu_used_current = gpu_hours_interval.quantize(Decimal("0.000001"))
        snapshot.gpu_used_interval = gpu_hours_interval.quantize(Decimal("0.000001"))
        snapshot.charge_interval = interval_charge.quantize(Decimal("0.000001"))
        snapshot.last_collected_at = now
        if mark_sent:
            snapshot.last_sent_at = now
            snapshot.total_charge_sent = (
                (snapshot.total_charge_sent or Decimal("0")) + sent_charge
            ).quantize(Decimal("0.000001"))
        db.commit()

    # ------------------------------------------------------------------
    # Per-row export
    # ------------------------------------------------------------------

    def _export_row(
        self,
        db: Session,
        *,
        row: GpuUsageRow,
        project: Project,
        username: str,
        resource: str,
        local_record_id: str,
    ) -> tuple[str, Decimal]:
        """Send one adjustment-debit record to AMIE for a single ClickHouse row.

        Returns ``(status, charge)`` where *status* is ``"sent"``, ``"failed"``,
        or ``"skipped"`` and *charge* is the computed allocation debit.
        """
        charge = (row.gpu_hours * self.gpu_charge_factor).quantize(Decimal("0.000001"))
        if charge <= Decimal("0"):
            logger.debug(
                "Skipping zero-charge row local_record_id=%s", local_record_id
            )
            return "skipped", Decimal("0")

        interval_start = datetime(
            row.date.year, row.date.month, row.date.day, tzinfo=UTC
        )
        interval_end = interval_start + timedelta(days=1)

        record = AdjustmentUsageRecord(
            adjustment_type="debit",
            charge=str(charge),
            start_time=interval_start.isoformat(),
            local_project_id=project.site_project_id,
            local_record_id=local_record_id,
            resource=resource,
            username=username,
            comment=(
                f"NRP GPU usage export for {row.date.isoformat()} "
                f"namespace={row.namespace}"
            ),
            local_reference=local_record_id,
        )

        logger.debug(
            "Sending AMIE usage record local_record_id=%s namespace=%s "
            "cilogon_id=%s username=%s charge=%s",
            local_record_id,
            row.namespace,
            row.created_by,
            username,
            charge,
        )

        with UsageClient(
            site_name=self.site_name, api_key=self.api_key, usage_url=self.usage_url
        ) as usage_client:
            responses = usage_client.send(record)

        validation_failed = any(r.failed_records for r in responses)
        status = "failed" if validation_failed else "sent"

        export_row = AMIEUsageExport(
            project_id=project.id,
            local_record_id=local_record_id,
            usage_type="adjustment",
            adjustment_type="debit",
            interval_start=interval_start,
            interval_end=interval_end,
            charge=charge,
            resource=resource,
            username=username,
            status=status,
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
        return status, charge

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def send_all_projects_usage(self, db: Session) -> dict[str, int]:
        """Query ClickHouse for the last interval and send AMIE usage records.

        For each ``(namespace, created_by, date)`` row returned by ClickHouse:

        1. Resolve the ``Project`` via ``kubernetes_namespace``.
        2. Resolve the ``User`` via ``User.remote_site_login == created_by``
           (the CILogon subject ID acquired during the OAuth invite flow).
        3. Determine the AMIE username from the user's ``ProjectUser``
           membership (``ProjectUser.remote_site_login``).
        4. Send one adjustment-debit record per row (idempotent via
           ``local_record_id`` uniqueness in ``amie_usage_exports``).
        5. Update each project's ``ProjectUsageSnapshot`` with aggregate GPU
           hours and charges for the interval.
        """
        enable_send = bool(self.api_key)
        if not enable_send:
            logger.warning(
                "AMIE_API_KEY is not configured; collecting usage snapshots "
                "without AMIE export."
            )

        interval_start, interval_end = self._current_interval()
        date_from, date_to = self._date_range(interval_start, interval_end)
        now = datetime.now(UTC)

        usage_rows = self.clickhouse.get_gpu_usage(date_from, date_to)

        # namespace → Project index
        namespace_to_project: dict[str, Project] = {
            p.kubernetes_namespace: p
            for p in db.query(Project).all()
            if p.kubernetes_namespace
        }
        # project.id → Project (for snapshot updates)
        id_to_project: dict = {p.id: p for p in namespace_to_project.values()}

        counters = {"updated": 0, "sent": 0, "failed": 0, "skipped": 0}

        # project.id → (total_gpu_hours, total_charge, sent_charge)
        project_totals: dict = {}

        for row in usage_rows:
            project = namespace_to_project.get(row.namespace)
            if project is None:
                logger.warning(
                    "No project found for namespace=%s; skipping row.", row.namespace
                )
                counters["skipped"] += 1
                continue

            if not project.site_project_id:
                logger.debug(
                    "Project %s has no site_project_id; skipping namespace=%s.",
                    project.id,
                    row.namespace,
                )
                counters["skipped"] += 1
                continue

            resource = settings.amie_gpu_resource_name or project.resource_type or ""
            if not resource:
                logger.debug(
                    "No AMIE resource name configured for project %s; skipping.",
                    project.id,
                )
                counters["skipped"] += 1
                continue

            user = (
                db.query(User)
                .filter(User.remote_site_login == row.created_by)
                .first()
            )
            if user is None:
                logger.warning(
                    "No user found for cilogon_id=%s namespace=%s; skipping.",
                    row.created_by,
                    row.namespace,
                )
                counters["skipped"] += 1
                continue

            local_record_id = self._local_record_id(project, row.created_by, row.date)

            if self._already_exported(db, local_record_id):
                logger.debug(
                    "Already exported local_record_id=%s; skipping.", local_record_id
                )
                counters["skipped"] += 1
                continue

            username = self._pick_username(user, project)
            row_charge = (row.gpu_hours * self.gpu_charge_factor).quantize(
                Decimal("0.000001")
            )

            # Accumulate totals for snapshot update regardless of send outcome
            pid = project.id
            gpu_acc, charge_acc, sent_acc = project_totals.get(
                pid, (Decimal("0"), Decimal("0"), Decimal("0"))
            )
            project_totals[pid] = (
                gpu_acc + row.gpu_hours,
                charge_acc + row_charge,
                sent_acc,
            )

            if not enable_send:
                counters["updated"] += 1
                counters["skipped"] += 1
                continue

            try:
                status, sent_charge = self._export_row(
                    db,
                    row=row,
                    project=project,
                    username=username,
                    resource=resource,
                    local_record_id=local_record_id,
                )
            except Exception:
                logger.exception(
                    "Failed exporting AMIE usage row local_record_id=%s",
                    local_record_id,
                )
                db.rollback()
                counters["failed"] += 1
                continue

            counters["updated"] += 1
            if status == "sent":
                counters["sent"] += 1
                # Add this row's charge to the project's sent total
                gpu_acc, charge_acc, sent_acc = project_totals[pid]
                project_totals[pid] = (gpu_acc, charge_acc, sent_acc + sent_charge)
            elif status == "failed":
                counters["failed"] += 1
            else:
                counters["skipped"] += 1

        # Update ProjectUsageSnapshot for every project that had ClickHouse rows
        for project_id, (gpu_hours, interval_charge, sent_charge) in project_totals.items():
            project = id_to_project.get(project_id)
            if project is None:
                project = db.query(Project).filter(Project.id == project_id).first()
            if project is None:
                continue
            try:
                self._upsert_usage_snapshot(
                    db,
                    project=project,
                    gpu_hours_interval=gpu_hours,
                    interval_charge=interval_charge,
                    sent_charge=sent_charge,
                    now=now,
                    mark_sent=enable_send and sent_charge > Decimal("0"),
                )
            except Exception:
                logger.exception(
                    "Failed updating usage snapshot for project %s", project_id
                )
                db.rollback()

        logger.info(
            "AMIE usage export cycle complete "
            "interval_start=%s date_from=%s date_to=%s "
            "updated=%d sent=%d failed=%d skipped=%d",
            interval_start.isoformat(),
            date_from,
            date_to,
            counters["updated"],
            counters["sent"],
            counters["failed"],
            counters["skipped"],
        )
        return counters
