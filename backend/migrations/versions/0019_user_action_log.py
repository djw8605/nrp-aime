"""Add user_action_logs table for tracking emails, OAuth flows, and other user-facing events.

Revision ID: 0019_user_action_log
Revises: 0018_project_admin_tags
Create Date: 2026-03-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0019_user_action_log"
down_revision = "0018_project_admin_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "user_action_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("event_type", sa.String(), nullable=False, index=True),
        sa.Column("event_status", sa.String(), nullable=False, server_default="info"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "event_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            index=True,
        ),
    )
    op.create_index(
        "ix_user_action_logs_event_status",
        "user_action_logs",
        ["event_status"],
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_table("user_action_logs")
