"""Add continuously updated per-project usage snapshots.

Revision ID: 0004_project_usage_snapshots
Revises: 0003_worker_statuses
Create Date: 2026-03-14 10:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_project_usage_snapshots"
down_revision = "0003_worker_statuses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "project_usage_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False, server_default=sa.text("60")),
        sa.Column("cpu_used_current", sa.Numeric(precision=18, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("gpu_used_current", sa.Numeric(precision=18, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("cpu_used_interval", sa.Numeric(precision=18, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("gpu_used_interval", sa.Numeric(precision=18, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("charge_interval", sa.Numeric(precision=18, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("total_charge_sent", sa.Numeric(precision=18, scale=6), nullable=False, server_default=sa.text("0")),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(
        op.f("ix_project_usage_snapshots_last_collected_at"),
        "project_usage_snapshots",
        ["last_collected_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_usage_snapshots_project_id"),
        "project_usage_snapshots",
        ["project_id"],
        unique=True,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(
        op.f("ix_project_usage_snapshots_project_id"),
        table_name="project_usage_snapshots",
    )
    op.drop_index(
        op.f("ix_project_usage_snapshots_last_collected_at"),
        table_name="project_usage_snapshots",
    )
    op.drop_table("project_usage_snapshots")
