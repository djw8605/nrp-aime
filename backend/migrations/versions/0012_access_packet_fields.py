"""Add ACCESS packet field columns for allocation and account packets.

Revision ID: 0012_access_packet_fields
Revises: 0011_invite_flow
Create Date: 2026-03-16 13:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_access_packet_fields"
down_revision = "0011_invite_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "amie_allocation_packets",
        sa.Column("allocated_resource", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_allocation_packets",
        sa.Column("charge_number", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_allocation_packets",
        sa.Column("proposal_number", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_allocation_packets",
        sa.Column("pi_global_id", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_allocation_packets",
        sa.Column("pi_title", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_allocation_packets",
        sa.Column(
            "sfos",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "amie_allocation_packets",
        sa.Column(
            "academic_degree",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )

    op.add_column(
        "amie_new_user_packets",
        sa.Column("allocated_resource", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_title", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_city", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_state", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_country", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_street_address", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_street_address2", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_zip", sa.String(), nullable=True),
    )
    op.add_column(
        "amie_new_user_packets",
        sa.Column("user_password_access_enable", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_column("amie_new_user_packets", "user_password_access_enable")
    op.drop_column("amie_new_user_packets", "user_zip")
    op.drop_column("amie_new_user_packets", "user_street_address2")
    op.drop_column("amie_new_user_packets", "user_street_address")
    op.drop_column("amie_new_user_packets", "user_country")
    op.drop_column("amie_new_user_packets", "user_state")
    op.drop_column("amie_new_user_packets", "user_city")
    op.drop_column("amie_new_user_packets", "user_title")
    op.drop_column("amie_new_user_packets", "allocated_resource")

    op.drop_column("amie_allocation_packets", "academic_degree")
    op.drop_column("amie_allocation_packets", "sfos")
    op.drop_column("amie_allocation_packets", "pi_title")
    op.drop_column("amie_allocation_packets", "pi_global_id")
    op.drop_column("amie_allocation_packets", "proposal_number")
    op.drop_column("amie_allocation_packets", "charge_number")
    op.drop_column("amie_allocation_packets", "allocated_resource")
