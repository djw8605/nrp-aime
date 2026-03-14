"""Add worker status heartbeat table.

Revision ID: 0003_worker_statuses
Revises: 0002_amie_usage_exports
Create Date: 2026-03-14 09:25:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_worker_statuses"
down_revision = "0002_amie_usage_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "worker_statuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_name", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("current_state", sa.String(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("state_payload", sa.JSON(), nullable=True),
        sa.Column(
            "last_heartbeat",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_worker_statuses_worker_name"),
        "worker_statuses",
        ["worker_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_worker_statuses_last_heartbeat"),
        "worker_statuses",
        ["last_heartbeat"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(
        op.f("ix_worker_statuses_last_heartbeat"), table_name="worker_statuses"
    )
    op.drop_index(op.f("ix_worker_statuses_worker_name"), table_name="worker_statuses")
    op.drop_table("worker_statuses")
