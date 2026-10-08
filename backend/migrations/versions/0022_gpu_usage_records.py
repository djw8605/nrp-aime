"""Add GPU usage ledger and per-project sync watermark.

Revision ID: 0022_gpu_usage_records
Revises: 0021_reset_unonboarded_pi_state
Create Date: 2026-10-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0022_gpu_usage_records"
down_revision = "0021_reset_unonboarded_pi_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "gpu_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("attribution", sa.String(), nullable=False),
        sa.Column("gpu_hours", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("charge", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("local_record_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("submitted_charge", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("accounting_db_record_id", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "usage_date",
            "username",
            name="uq_gpu_usage_project_date_username",
        ),
    )
    op.create_index(
        op.f("ix_gpu_usage_records_local_record_id"),
        "gpu_usage_records",
        ["local_record_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_gpu_usage_records_project_id"),
        "gpu_usage_records",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gpu_usage_records_usage_date"),
        "gpu_usage_records",
        ["usage_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_gpu_usage_records_status"),
        "gpu_usage_records",
        ["status"],
        unique=False,
    )
    op.add_column(
        "projects",
        sa.Column("gpu_usage_synced_through", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_column("projects", "gpu_usage_synced_through")
    op.drop_index(op.f("ix_gpu_usage_records_status"), table_name="gpu_usage_records")
    op.drop_index(op.f("ix_gpu_usage_records_usage_date"), table_name="gpu_usage_records")
    op.drop_index(op.f("ix_gpu_usage_records_project_id"), table_name="gpu_usage_records")
    op.drop_index(
        op.f("ix_gpu_usage_records_local_record_id"), table_name="gpu_usage_records"
    )
    op.drop_table("gpu_usage_records")
