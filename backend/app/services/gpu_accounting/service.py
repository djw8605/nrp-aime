"""GPU-hour accounting export: NRP accounting API → ledger → ACCESS.

Each cycle:
1. ``sync_ledger`` pulls daily GPU usage for GPU allocations, attributes it to
   AMIE usernames, and upserts ``gpu_usage_records``.
2. ``submit_pending`` posts pending/failed records as Compute usage.
3. ``reconcile`` marks records loaded/failed from ``/usage/loaded`` and
   ``/usage/status``.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import NamedTuple

from amieclient.usage import ComputeUsageRecord, UsageLoadedRecord
from sqlalchemy.orm import Session

from app.config import settings
from app.models.gpu_usage_record import GpuUsageRecord
from app.models.project import Project
from app.services.aime.usage_api import (
    MAX_RECORDS_PER_POST,
    AccessUsageApiClient,
    UsageApiError,
    iso_utc,
)
from app.services.gpu_accounting.attribution import GpuUsageAttributor
from app.services.gpu_accounting.scope import is_exportable_gpu_project
from app.services.nrp_accounting.client import GpuUsageRow, NrpAccountingClient

logger = logging.getLogger(__name__)

QUANT = Decimal("0.000001")
PI_LOGIN_MISSING = "PI has no site login yet"
# A /usage/loaded charge within this of the submitted charge confirms the load
# (ACCESS may store Charge at lower precision than the 6 decimals we send).
LOADED_CHARGE_TOLERANCE = Decimal("0.01")
# Submitted rows older than the reconcile look-back are checked one by one.
RECONCILE_STALE_LOOKUPS_PER_CYCLE = 200
# /usage/status is queried from this long before a batch's submitted_at.
STATUS_WINDOW_LEAD = timedelta(minutes=5)

# (usage_date, username) -> (gpu_hours, attribution)
DesiredRecords = dict[tuple[date, str], tuple[Decimal, str]]


def _as_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class _Window(NamedTuple):
    """A project's full allocation window and (optional) range to re-fetch."""

    project: Project
    alloc_start: date
    alloc_end: date
    fetch_start: date | None  # None: nothing to fetch this cycle


class GpuAccountingService:
    """Syncs, submits, and reconciles GPU usage for GPU allocations."""

    def __init__(
        self,
        *,
        accounting_client: NrpAccountingClient | None = None,
        usage_client: AccessUsageApiClient | None = None,
    ) -> None:
        self.accounting = accounting_client or NrpAccountingClient()
        self.usage = usage_client or AccessUsageApiClient()
        self.resource = settings.amie_gpu_resource_name
        self.charge_factor = Decimal(str(settings.amie_usage_gpu_charge_factor))
        self.restatement_days = max(0, settings.amie_usage_restatement_days)
        self.reconcile_lookback_days = max(1, settings.amie_usage_reconcile_lookback_days)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def local_record_id(project: Project, usage_date: date, username: str) -> str:
        """Stable ACCESS LocalRecordID for one project/day/username."""
        user_hash = hashlib.sha256(username.encode()).hexdigest()[:12]
        return f"nrp-gpu-{project.site_project_id}-{usage_date:%Y%m%d}-{user_hash}"

    def _charge(self, gpu_hours: Decimal) -> Decimal:
        return (gpu_hours * self.charge_factor).quantize(QUANT)

    def _window(self, project: Project, latest: date) -> _Window | None:
        """Full allocation window plus fetch start for *project*, or None."""
        start = project.start_date
        if start is None and project.created_at is not None:
            start = project.created_at.date()
        if start is None:
            return None
        end = min(project.end_date or latest, latest)
        if start > end:
            return None
        fetch_start: date | None = start
        if project.gpu_usage_synced_through is not None:
            fetch_start = max(
                start,
                project.gpu_usage_synced_through - timedelta(days=self.restatement_days),
            )
            if fetch_start > end:
                fetch_start = None
        return _Window(project, start, end, fetch_start)

    # ------------------------------------------------------------------
    # Ledger sync
    # ------------------------------------------------------------------

    def sync_ledger(self, db: Session) -> dict[str, int]:
        """Pull GPU usage and upsert ledger rows for every exportable GPU project."""
        counters = {"projects": 0, "rows": 0, "dropped": 0, "records_changed": 0}
        latest = self.accounting.latest_data_date()

        # Full allocation windows for every exportable project: they decide which
        # project owns a usage row, even when that project has nothing to fetch.
        by_namespace: dict[str, list[_Window]] = defaultdict(list)
        for project in db.query(Project).all():
            if not is_exportable_gpu_project(project):
                continue
            window = self._window(project, latest)
            if window is not None:
                by_namespace[project.kubernetes_namespace].append(window)

        windows: dict[uuid.UUID, _Window] = {
            w.project.id: w
            for entries in by_namespace.values()
            for w in entries
            if w.fetch_start is not None
        }
        if not windows:
            return counters

        range_start = min(w.fetch_start for w in windows.values())
        range_end = max(w.alloc_end for w in windows.values())
        rows = self.accounting.gpu_usage(
            sorted({w.project.kubernetes_namespace for w in windows.values()}),
            range_start,
            range_end,
        )
        holders = self._ledger_holders(db, by_namespace, range_start, range_end)

        attributor = GpuUsageAttributor(db)
        desired: dict[uuid.UUID, DesiredRecords] = defaultdict(dict)
        pi_missing_from: dict[uuid.UUID, date] = {}
        for row in rows:
            owner = self._owner_for_row(row, by_namespace, holders)
            if owner is None or owner.fetch_start is None or row.date < owner.fetch_start:
                # No owner, or the owner already holds this date in its ledger;
                # never fall through to another project (would double count).
                continue
            project = owner.project
            attribution = attributor.attribute(project, row.created_by)
            if attribution is None:
                counters["dropped"] += 1
                logger.info(
                    "Dropping GPU usage for non-member namespace=%s created_by=%s date=%s hours=%s",
                    row.namespace,
                    row.created_by,
                    row.date,
                    row.gpu_hours,
                )
                continue
            counters["rows"] += 1
            key = (row.date, attribution.username)
            hours, _ = desired[project.id].get(key, (Decimal("0"), attribution.attribution))
            desired[project.id][key] = (hours + row.gpu_hours, attribution.attribution)
            if not attribution.username:
                pi_missing_from[project.id] = min(row.date, pi_missing_from.get(project.id, row.date))

        for project_id, window in windows.items():
            project = window.project
            counters["records_changed"] += self._apply(
                db, project, window.fetch_start, window.alloc_end, desired.get(project_id, {})
            )
            missing = pi_missing_from.get(project_id)
            if missing is None:
                project.gpu_usage_synced_through = latest
            else:
                # Hold the watermark so the next fetch re-reads the PI-pending days.
                project.gpu_usage_synced_through = min(
                    latest, missing + timedelta(days=self.restatement_days)
                )
            counters["projects"] += 1

        db.commit()
        return counters

    @staticmethod
    def _ledger_holders(
        db: Session,
        by_namespace: dict[str, list[_Window]],
        range_start: date,
        range_end: date,
    ) -> dict[tuple[str, date], set[uuid.UUID]]:
        """(namespace, usage_date) -> ids of projects that already hold ledger rows."""
        namespace_of = {
            w.project.id: namespace
            for namespace, entries in by_namespace.items()
            if len(entries) > 1  # ownership only matters when a namespace is shared
            for w in entries
        }
        holders: dict[tuple[str, date], set[uuid.UUID]] = defaultdict(set)
        if not namespace_of:
            return holders
        query = (
            db.query(GpuUsageRecord.project_id, GpuUsageRecord.usage_date)
            .filter(
                GpuUsageRecord.project_id.in_(list(namespace_of)),
                GpuUsageRecord.usage_date >= range_start,
                GpuUsageRecord.usage_date <= range_end,
            )
            .distinct()
        )
        for project_id, usage_date in query:
            holders[(namespace_of[project_id], usage_date)].add(project_id)
        return holders

    @staticmethod
    def _owner_for_row(
        row: GpuUsageRow,
        by_namespace: dict[str, list[_Window]],
        holders: dict[tuple[str, date], set[uuid.UUID]],
    ) -> _Window | None:
        """The single project owning *row*.

        A project that already has ledger rows for the date keeps it; otherwise
        (and among equals) the latest allocation start wins, then the lowest id.
        """
        candidates = [
            w
            for w in by_namespace.get(row.namespace, [])
            if w.alloc_start <= row.date <= w.alloc_end
        ]
        held = holders.get((row.namespace, row.date))
        if held:
            holding = [w for w in candidates if w.project.id in held]
            candidates = holding or candidates
        if not candidates:
            return None
        latest_start = max(w.alloc_start for w in candidates)
        return min(
            (w for w in candidates if w.alloc_start == latest_start),
            key=lambda w: str(w.project.id),
        )

    def _apply(
        self,
        db: Session,
        project: Project,
        start: date,
        end: date,
        desired: DesiredRecords,
    ) -> int:
        """Upsert ledger rows for *project* within [start, end]; return change count."""
        existing = {
            (record.usage_date, record.username): record
            for record in db.query(GpuUsageRecord)
            .filter(
                GpuUsageRecord.project_id == project.id,
                GpuUsageRecord.usage_date >= start,
                GpuUsageRecord.usage_date <= end,
            )
            .all()
        }
        changed = 0

        for key, record in existing.items():
            if key in desired:
                continue
            if record.submitted_charge is None:
                db.delete(record)
                changed += 1
            elif Decimal(record.gpu_hours).quantize(QUANT) != Decimal("0").quantize(QUANT):
                self._set_hours(record, Decimal("0").quantize(QUANT))
                changed += 1

        for (usage_date, username), (hours, attribution) in desired.items():
            hours = hours.quantize(QUANT)
            record = existing.get((usage_date, username))
            if record is None:
                db.add(
                    GpuUsageRecord(
                        project_id=project.id,
                        usage_date=usage_date,
                        username=username,
                        attribution=attribution,
                        gpu_hours=hours,
                        charge=self._charge(hours),
                        local_record_id=self.local_record_id(project, usage_date, username),
                        status=GpuUsageRecord.STATUS_PENDING,
                        attempts=0,
                        last_error=None if username else PI_LOGIN_MISSING,
                    )
                )
                changed += 1
            elif Decimal(record.gpu_hours).quantize(QUANT) != hours:
                self._set_hours(record, hours)
                changed += 1
        db.flush()
        return changed

    def _set_hours(self, record: GpuUsageRecord, hours: Decimal) -> None:
        record.gpu_hours = hours
        record.charge = self._charge(hours)
        record.status = GpuUsageRecord.STATUS_PENDING
        record.last_error = None if record.username else PI_LOGIN_MISSING

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _compute_record(self, record: GpuUsageRecord) -> ComputeUsageRecord:
        """Build one ACCESS Compute usage record (a whole UTC day) for a ledger row."""
        start = datetime.combine(record.usage_date, time.min, tzinfo=UTC)
        return ComputeUsageRecord(
            username=record.username,
            local_project_id=record.project.site_project_id,
            local_record_id=record.local_record_id,
            local_reference=str(record.id),
            resource=self.resource,
            submit_time=iso_utc(start),
            start_time=iso_utc(start),
            end_time=iso_utc(start + timedelta(days=1)),
            charge=str(Decimal(record.charge).quantize(QUANT)),
            node_count=1,
            queue="gpu",
            job_name="nrp-gpu-daily",
        )

    def submit_pending(self, db: Session) -> dict[str, int]:
        """POST pending and failed ledger rows to ACCESS as Compute records."""
        counters = {"submitted": 0, "failed": 0}
        candidates = (
            db.query(GpuUsageRecord)
            .filter(
                GpuUsageRecord.status.in_(
                    [GpuUsageRecord.STATUS_PENDING, GpuUsageRecord.STATUS_FAILED]
                ),
                GpuUsageRecord.username != "",
            )
            .order_by(GpuUsageRecord.usage_date, GpuUsageRecord.local_record_id)
            .all()
        )
        # Zero-charge rows are only sent to overwrite a previously sent charge.
        sendable = [
            record
            for record in candidates
            if Decimal(record.charge) > 0 or record.submitted_charge is not None
        ]

        for offset in range(0, len(sendable), MAX_RECORDS_PER_POST):
            batch = sendable[offset : offset + MAX_RECORDS_PER_POST]
            now = datetime.now(UTC)
            try:
                failures = self.usage.post_compute([self._compute_record(r) for r in batch])
            except UsageApiError as exc:
                logger.error("ACCESS usage POST failed for %d records: %s", len(batch), exc)
                for record in batch:
                    record.status = GpuUsageRecord.STATUS_FAILED
                    record.last_error = str(exc)
                    record.attempts = (record.attempts or 0) + 1
                counters["failed"] += len(batch)
                db.commit()
                continue

            errors = {
                str(failure.record.local_record_id): str(failure.error or "validation failed")
                for failure in failures
            }
            for record in batch:
                record.attempts = (record.attempts or 0) + 1
                if record.local_record_id in errors:
                    record.status = GpuUsageRecord.STATUS_FAILED
                    record.last_error = errors[record.local_record_id]
                    counters["failed"] += 1
                else:
                    record.status = GpuUsageRecord.STATUS_SUBMITTED
                    record.submitted_charge = record.charge
                    record.submitted_at = now
                    record.loaded_at = None
                    record.accounting_db_record_id = None
                    record.last_error = None
                    counters["submitted"] += 1
            db.commit()
        return counters

    # ------------------------------------------------------------------
    # Reconcile
    # ------------------------------------------------------------------

    def _loaded_matches(self, record: GpuUsageRecord, item: UsageLoadedRecord) -> bool:
        """True when *item* confirms ACCESS loaded *record*'s submitted charge."""
        if str(item.local_record_id) != record.local_record_id:
            return False
        if str(item.resource or self.resource) != self.resource:
            return False
        if record.submitted_charge is None:
            return False
        try:
            charge = Decimal(str(item.charge))
        except ArithmeticError:
            return False
        if not charge.is_finite():
            return False
        # ACCESS may store Charge at lower precision than we send.
        return abs(charge - Decimal(record.submitted_charge)) < LOADED_CHARGE_TOLERANCE

    @staticmethod
    def _mark_loaded(record: GpuUsageRecord, item: UsageLoadedRecord, now: datetime) -> None:
        record.status = GpuUsageRecord.STATUS_LOADED
        record.accounting_db_record_id = (
            str(item.accounting_db_record_id) if item.accounting_db_record_id else None
        )
        record.loaded_at = now
        record.last_error = None

    def reconcile(
        self, db: Session, *, cycle_started_at: datetime | None = None
    ) -> dict[str, int]:
        """Mark submitted rows loaded/failed using ACCESS load status.

        Rows submitted within the look-back window are matched against one bulk
        ``/usage/loaded`` query; older rows are looked up one by one (capped per
        cycle). ``/usage/status`` errors only apply to the submission batch whose
        window they fall in, and batches sent after *cycle_started_at* are not
        status-checked yet (ACCESS loads asynchronously).
        """
        counters = {"loaded": 0, "load_failed": 0}
        submitted = (
            db.query(GpuUsageRecord)
            .filter(GpuUsageRecord.status == GpuUsageRecord.STATUS_SUBMITTED)
            .all()
        )
        if not submitted:
            return counters

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=self.reconcile_lookback_days)

        def sent_at(record: GpuUsageRecord) -> datetime:
            return _as_utc(record.submitted_at) if record.submitted_at else now

        # Loaded wins: process it first so a status error can't override it.
        since = max(min(sent_at(r) for r in submitted) - timedelta(hours=1), cutoff)
        by_id = {record.local_record_id: record for record in submitted}
        try:
            loaded = self.usage.loaded(since)
        except UsageApiError:
            logger.exception("ACCESS usage/loaded reconcile failed")
            loaded = []
        for item in loaded:
            record = by_id.get(str(item.local_record_id))
            if record is None or record.status != GpuUsageRecord.STATUS_SUBMITTED:
                continue
            if self._loaded_matches(record, item):
                self._mark_loaded(record, item, now)
                counters["loaded"] += 1

        pending = [r for r in submitted if r.status == GpuUsageRecord.STATUS_SUBMITTED]
        stale = sorted((r for r in pending if sent_at(r) < cutoff), key=sent_at)
        for record in stale[:RECONCILE_STALE_LOOKUPS_PER_CYCLE]:
            try:
                item = self.usage.loaded_record(record.local_record_id)
            except UsageApiError:
                logger.exception(
                    "ACCESS usage/loaded lookup failed for %s", record.local_record_id
                )
                continue
            if item is not None and self._loaded_matches(record, item):
                self._mark_loaded(record, item, now)
                counters["loaded"] += 1

        # Rows from one POST batch share submitted_at; a batch's errors can only
        # appear after it was sent, so query status per batch from just before it.
        groups: dict[datetime, dict[str, GpuUsageRecord]] = defaultdict(dict)
        for record in pending:
            if record.status != GpuUsageRecord.STATUS_SUBMITTED:
                continue
            when = sent_at(record)
            if when < cutoff:
                continue
            if cycle_started_at is not None and when >= cycle_started_at:
                continue
            groups[when][record.local_record_id] = record
        for when in sorted(groups):
            try:
                statuses = self.usage.status(when - STATUS_WINDOW_LEAD, now)
            except UsageApiError:
                logger.exception("ACCESS usage/status reconcile failed for batch sent %s", when)
                continue
            group = groups[when]
            for resource in statuses:
                if str(resource.resource or self.resource) != self.resource:
                    continue
                for error in resource.errors:
                    message = str(error.error or "load failed")
                    for failed in error.message.records:
                        record = group.get(str(failed.local_record_id))
                        if record is None or record.status != GpuUsageRecord.STATUS_SUBMITTED:
                            continue
                        record.status = GpuUsageRecord.STATUS_FAILED
                        record.last_error = message
                        counters["load_failed"] += 1

        db.commit()
        return counters

    # ------------------------------------------------------------------
    # Cycle
    # ------------------------------------------------------------------

    def run_cycle(self, db: Session) -> dict[str, int]:
        """Sync the ledger, then submit and reconcile when an API key is set."""
        counters = {
            "projects": 0,
            "rows": 0,
            "dropped": 0,
            "records_changed": 0,
            "submitted": 0,
            "failed": 0,
            "loaded": 0,
            "load_failed": 0,
        }
        cycle_started_at = datetime.now(UTC)
        counters.update(self.sync_ledger(db))
        if not self.usage.api_key:
            logger.warning(
                "AMIE_API_KEY is not configured; GPU usage ledger updated "
                "without submitting to ACCESS."
            )
            return counters
        counters.update(self.submit_pending(db))
        counters.update(self.reconcile(db, cycle_started_at=cycle_started_at))
        logger.info("GPU accounting cycle complete: %s", counters)
        return counters
