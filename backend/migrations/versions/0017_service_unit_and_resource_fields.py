"""Add parsed service-unit and allocated-resource fields.

Revision ID: 0017_su_resource_fields
Revises: 0016_multi_site_tags
Create Date: 2026-03-16 23:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0017_su_resource_fields"
down_revision = "0016_multi_site_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "projects",
        sa.Column("allocated_resource", sa.String(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("service_units_remaining", sa.Numeric(18, 4), nullable=True),
    )

    op.add_column(
        "project_users",
        sa.Column("allocated_resource", sa.String(), nullable=True),
    )
    op.add_column(
        "project_users",
        sa.Column("service_units_allocated", sa.Numeric(18, 4), nullable=True),
    )
    op.add_column(
        "project_users",
        sa.Column("service_units_remaining", sa.Numeric(18, 4), nullable=True),
    )

    op.add_column(
        "amie_new_user_packets",
        sa.Column("service_units_allocated", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("service_units_remaining", sa.String(), nullable=True),
    )

    op.add_column(
        "amie_lifecycle_packets",
        sa.Column("grant_number", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_lifecycle_packets",
        sa.Column("allocated_resource", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_lifecycle_packets",
        sa.Column("service_units_allocated", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_lifecycle_packets",
        sa.Column("service_units_remaining", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_lifecycle_packets",
        sa.Column("start_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "amie_lifecycle_packets",
        sa.Column("end_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "amie_allocation_packets",
        sa.Column("service_units_remaining", sa.String(), nullable=True),
    )
    op.create_index(
        op.f("ix_amie_lifecycle_packets_grant_number"),
        "amie_lifecycle_packets",
        ["grant_number"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(
        op.f("ix_amie_lifecycle_packets_grant_number"),
        table_name="amie_lifecycle_packets",
    )
    op.drop_column("amie_lifecycle_packets", "end_date")
    op.drop_column("amie_lifecycle_packets", "start_date")
    op.drop_column("amie_lifecycle_packets", "service_units_remaining")
    op.drop_column("amie_lifecycle_packets", "service_units_allocated")
    op.drop_column("amie_lifecycle_packets", "allocated_resource")
    op.drop_column("amie_lifecycle_packets", "grant_number")

    op.drop_column("amie_new_user_packets", "service_units_remaining")
    op.drop_column("amie_new_user_packets", "service_units_allocated")

    op.drop_column("amie_allocation_packets", "service_units_remaining")

    op.drop_column("project_users", "service_units_remaining")
    op.drop_column("project_users", "service_units_allocated")
    op.drop_column("project_users", "allocated_resource")

    op.drop_column("projects", "service_units_remaining")
    op.drop_column("projects", "allocated_resource")
