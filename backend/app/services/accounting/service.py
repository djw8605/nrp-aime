"""Stub accounting data collection service.

This service provides a deterministic placeholder data source for
"current usage" values until a production accounting integration is wired in.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.models.project import Project
from app.models.project_usage_snapshot import ProjectUsageSnapshot


class AccountingService:
    """Collect and expose accounting usage values for projects."""

    def __init__(self) -> None:
        self.stub_enabled = settings.accounting_stub_enabled
        self.cpu_ratio = self._clamp_ratio(settings.accounting_stub_cpu_ratio)
        self.gpu_ratio = self._clamp_ratio(settings.accounting_stub_gpu_ratio)

    @staticmethod
    def _clamp_ratio(value: float) -> Decimal:
        ratio = Decimal(str(value))
        if ratio < Decimal("0"):
            return Decimal("0")
        if ratio > Decimal("1"):
            return Decimal("1")
        return ratio

    @staticmethod
    def _to_decimal(value: int | float | Decimal | None) -> Decimal:
        if value is None:
            return Decimal("0")
        return Decimal(str(value))

    def _stub_usage_for_project(self, project: Project) -> tuple[Decimal, Decimal]:
        cpu_alloc = self._to_decimal(project.cpu_allocated)
        gpu_alloc = self._to_decimal(project.gpu_allocated)
        cpu_used = (cpu_alloc * self.cpu_ratio).quantize(Decimal("0.000001"))
        gpu_used = (gpu_alloc * self.gpu_ratio).quantize(Decimal("0.000001"))
        return cpu_used, gpu_used

    def _get_or_create_snapshot(
        self,
        db: Session,
        *,
        project: Project,
    ) -> ProjectUsageSnapshot:
        snapshot = (
            db.query(ProjectUsageSnapshot)
            .filter(ProjectUsageSnapshot.project_id == project.id)
            .first()
        )
        if snapshot is None:
            snapshot = ProjectUsageSnapshot(project_id=project.id)
            db.add(snapshot)
            db.flush()
        return snapshot

    def refresh_project_stub_snapshot(
        self,
        db: Session,
        *,
        project: Project,
    ) -> ProjectUsageSnapshot:
        """Update one project's snapshot using deterministic stub usage."""
        snapshot = self._get_or_create_snapshot(db, project=project)
        cpu_used, gpu_used = self._stub_usage_for_project(project)
        snapshot.interval_minutes = max(1, settings.amie_usage_interval_minutes)
        snapshot.cpu_used_current = cpu_used
        snapshot.gpu_used_current = gpu_used
        snapshot.cpu_used_interval = Decimal("0")
        snapshot.gpu_used_interval = Decimal("0")
        snapshot.charge_interval = Decimal("0")
        snapshot.last_collected_at = datetime.now(UTC)
        return snapshot

    def refresh_all_stub_snapshots(self, db: Session) -> dict[str, int]:
        """Refresh stub accounting snapshots for every project."""
        if not self.stub_enabled:
            return {"updated": 0, "skipped": 0}

        updated = 0
        skipped = 0
        for project in db.query(Project).all():
            existing_snapshot = (
                db.query(ProjectUsageSnapshot)
                .filter(ProjectUsageSnapshot.project_id == project.id)
                .first()
            )
            if existing_snapshot is not None:
                skipped += 1
                continue
            self.refresh_project_stub_snapshot(db, project=project)
            updated += 1
        db.commit()
        return {"updated": updated, "skipped": skipped}

    def project_current_usage(
        self,
        db: Session,
        *,
        project: Project,
    ) -> tuple[float, float, str, datetime | None]:
        """Return current usage + source metadata for a project."""
        snapshot = getattr(project, "usage_snapshot", None)
        if snapshot is None:
            snapshot = (
                db.query(ProjectUsageSnapshot)
                .filter(ProjectUsageSnapshot.project_id == project.id)
                .first()
            )
        if snapshot is not None:
            return (
                float(snapshot.cpu_used_current),
                float(snapshot.gpu_used_current),
                "usage_snapshot",
                snapshot.last_collected_at,
            )

        if not self.stub_enabled:
            return (0.0, 0.0, "none", None)

        cpu_used, gpu_used = self._stub_usage_for_project(project)
        return (float(cpu_used), float(gpu_used), "accounting_stub", None)
