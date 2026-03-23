"""Add custom admin tags to projects and users.

Revision ID: 0018_project_admin_tags
Revises: 0017_su_resource_fields
Create Date: 2026-03-21 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0018_project_admin_tags"
down_revision = "0017_su_resource_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "projects",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.alter_column("projects", "tags", server_default=None)

    op.add_column(
        "users",
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.alter_column("users", "tags", server_default=None)


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_column("users", "tags")
    op.drop_column("projects", "tags")
