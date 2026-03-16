"""Support person-scoped invites with optional project linkage.

Revision ID: 0014_person_invites
Revises: 0013_acct_state_invite
Create Date: 2026-03-16 18:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0014_person_invites"
down_revision = "0013_acct_state_invite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "project_invites",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_project_invites_user_id_users",
        "project_invites",
        "users",
        ["user_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_project_invites_user_id"),
        "project_invites",
        ["user_id"],
        unique=False,
    )
    op.alter_column(
        "project_invites",
        "project_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.execute("DELETE FROM project_invites WHERE project_id IS NULL")
    op.alter_column(
        "project_invites",
        "project_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_index(op.f("ix_project_invites_user_id"), table_name="project_invites")
    op.drop_constraint(
        "fk_project_invites_user_id_users",
        "project_invites",
        type_="foreignkey",
    )
    op.drop_column("project_invites", "user_id")
