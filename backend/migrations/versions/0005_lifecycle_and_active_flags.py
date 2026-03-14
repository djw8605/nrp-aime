"""Add lifecycle packet table and active/status fields.

Revision ID: 0005_lifecycle_and_active_flags
Revises: 0004_project_usage_snapshots
Create Date: 2026-03-14 20:35:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_lifecycle_and_active_flags"
down_revision = "0004_project_usage_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "amie_lifecycle_packets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("packet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("packet_type", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("person_id", sa.String(), nullable=True),
        sa.Column("keep_person_id", sa.String(), nullable=True),
        sa.Column("delete_person_id", sa.String(), nullable=True),
        sa.Column("action_type", sa.String(), nullable=True),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("dn_list", sa.JSON(), nullable=True),
        sa.Column("status_code", sa.String(), nullable=True),
        sa.Column("detail_code", sa.String(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("raw_body", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["packet_id"], ["amie_packets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("packet_id"),
    )
    op.create_index(
        op.f("ix_amie_lifecycle_packets_packet_type"),
        "amie_lifecycle_packets",
        ["packet_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_lifecycle_packets_project_id"),
        "amie_lifecycle_packets",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_lifecycle_packets_person_id"),
        "amie_lifecycle_packets",
        ["person_id"],
        unique=False,
    )

    op.add_column(
        "projects",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.add_column("users", sa.Column("department", sa.String(), nullable=True))
    op.add_column("users", sa.Column("nsf_status_code", sa.String(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "dn_list",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'::json"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    op.add_column(
        "project_users",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_column("project_users", "is_active")

    op.drop_column("users", "is_active")
    op.drop_column("users", "dn_list")
    op.drop_column("users", "nsf_status_code")
    op.drop_column("users", "department")

    op.drop_column("projects", "is_active")

    op.drop_index(
        op.f("ix_amie_lifecycle_packets_person_id"),
        table_name="amie_lifecycle_packets",
    )
    op.drop_index(
        op.f("ix_amie_lifecycle_packets_project_id"),
        table_name="amie_lifecycle_packets",
    )
    op.drop_index(
        op.f("ix_amie_lifecycle_packets_packet_type"),
        table_name="amie_lifecycle_packets",
    )
    op.drop_table("amie_lifecycle_packets")
