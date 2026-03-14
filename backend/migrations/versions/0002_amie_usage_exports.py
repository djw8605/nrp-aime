"""Add AMIE usage export tracking table.

Revision ID: 0002_amie_usage_exports
Revises: 0001_amie_packet_layout
Create Date: 2026-03-13 20:05:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_amie_usage_exports"
down_revision = "0001_amie_packet_layout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "amie_usage_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_record_id", sa.String(), nullable=False),
        sa.Column("usage_type", sa.String(), nullable=False),
        sa.Column("adjustment_type", sa.String(), nullable=False),
        sa.Column("interval_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("charge", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("resource", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_amie_usage_exports_local_record_id"),
        "amie_usage_exports",
        ["local_record_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_amie_usage_exports_project_id"),
        "amie_usage_exports",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_usage_exports_status"),
        "amie_usage_exports",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(op.f("ix_amie_usage_exports_status"), table_name="amie_usage_exports")
    op.drop_index(
        op.f("ix_amie_usage_exports_project_id"), table_name="amie_usage_exports"
    )
    op.drop_index(
        op.f("ix_amie_usage_exports_local_record_id"),
        table_name="amie_usage_exports",
    )
    op.drop_table("amie_usage_exports")
