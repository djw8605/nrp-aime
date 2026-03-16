"""Add project provisioning state and infrastructure tracking fields.

Revision ID: 0015_project_provisioning
Revises: 0014_person_invites
Create Date: 2026-03-16 20:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_project_provisioning"
down_revision = "0014_person_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "projects",
        sa.Column("authentik_group_name", sa.String(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "provisioning_state",
            sa.String(length=32),
            nullable=False,
            server_default="received",
        ),
    )
    op.add_column(
        "projects",
        sa.Column("provisioning_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("provisioning_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("provisioning_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("provisioning_last_error", sa.String(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("provisioning_alerted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("projects", "provisioning_state", server_default=None)


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_column("projects", "provisioning_alerted_at")
    op.drop_column("projects", "provisioning_last_error")
    op.drop_column("projects", "provisioning_completed_at")
    op.drop_column("projects", "provisioning_started_at")
    op.drop_column("projects", "provisioning_requested_at")
    op.drop_column("projects", "provisioning_state")
    op.drop_column("projects", "authentik_group_name")
