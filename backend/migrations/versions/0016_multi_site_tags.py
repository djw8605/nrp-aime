"""Add multi-site source tagging and user service-unit tracking.

Revision ID: 0016_multi_site_tags
Revises: 0015_project_provisioning
Create Date: 2026-03-16 22:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0016_multi_site_tags"
down_revision = "0015_project_provisioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    # Multi-site ingestion can reuse identifiers across sites.
    # Relax global unique indexes so records can coexist.
    op.drop_index(op.f("ix_projects_aime_allocation_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_allocation_record_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_grant_number"), table_name="projects")
    op.drop_index(op.f("ix_projects_site_project_id"), table_name="projects")
    op.drop_index(op.f("ix_users_person_id"), table_name="users")

    op.create_index(
        op.f("ix_projects_aime_allocation_id"),
        "projects",
        ["aime_allocation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projects_allocation_record_id"),
        "projects",
        ["allocation_record_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projects_grant_number"),
        "projects",
        ["grant_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projects_site_project_id"),
        "projects",
        ["site_project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_users_person_id"),
        "users",
        ["person_id"],
        unique=False,
    )

    op.add_column(
        "projects",
        sa.Column("source_site_name", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_projects_source_site_name"),
        "projects",
        ["source_site_name"],
        unique=False,
    )

    op.add_column(
        "users",
        sa.Column("source_site_name", sa.String(), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("service_units_allocated", sa.Numeric(18, 4), nullable=True),
    )
    op.create_index(
        op.f("ix_users_source_site_name"),
        "users",
        ["source_site_name"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(op.f("ix_users_source_site_name"), table_name="users")
    op.drop_column("users", "service_units_allocated")
    op.drop_column("users", "source_site_name")

    op.drop_index(op.f("ix_projects_source_site_name"), table_name="projects")
    op.drop_column("projects", "source_site_name")

    op.drop_index(op.f("ix_users_person_id"), table_name="users")
    op.drop_index(op.f("ix_projects_site_project_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_grant_number"), table_name="projects")
    op.drop_index(op.f("ix_projects_allocation_record_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_aime_allocation_id"), table_name="projects")

    op.create_index(
        op.f("ix_users_person_id"),
        "users",
        ["person_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_projects_site_project_id"),
        "projects",
        ["site_project_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_projects_grant_number"),
        "projects",
        ["grant_number"],
        unique=True,
    )
    op.create_index(
        op.f("ix_projects_allocation_record_id"),
        "projects",
        ["allocation_record_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_projects_aime_allocation_id"),
        "projects",
        ["aime_allocation_id"],
        unique=True,
    )
