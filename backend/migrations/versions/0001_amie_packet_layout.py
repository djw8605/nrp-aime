"""Create AMIE packet-aware schema.

Revision ID: 0001_amie_packet_layout
Revises:
Create Date: 2026-03-13 19:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_amie_packet_layout"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "amie_packets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("packet_rec_id", sa.BigInteger(), nullable=False),
        sa.Column("trans_rec_id", sa.BigInteger(), nullable=True),
        sa.Column("packet_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("packet_type", sa.String(), nullable=False),
        sa.Column("local_site_name", sa.String(), nullable=True),
        sa.Column("remote_site_name", sa.String(), nullable=True),
        sa.Column("originating_site_name", sa.String(), nullable=True),
        sa.Column("outgoing_flag", sa.Boolean(), nullable=True),
        sa.Column("transaction_state", sa.String(), nullable=True),
        sa.Column("packet_state", sa.String(), nullable=True),
        sa.Column("client_state", sa.String(), nullable=True),
        sa.Column("packet_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_packet", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_amie_packets_packet_rec_id"), "amie_packets", ["packet_rec_id"], unique=True)
    op.create_index(op.f("ix_amie_packets_packet_type"), "amie_packets", ["packet_type"], unique=False)
    op.create_index(op.f("ix_amie_packets_trans_rec_id"), "amie_packets", ["trans_rec_id"], unique=False)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aime_allocation_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("grant_number", sa.String(), nullable=True),
        sa.Column("allocation_record_id", sa.String(), nullable=True),
        sa.Column("site_project_id", sa.String(), nullable=True),
        sa.Column("allocation_type", sa.String(), nullable=True),
        sa.Column("request_type", sa.String(), nullable=True),
        sa.Column("service_units_allocated", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("project_title", sa.String(), nullable=True),
        sa.Column("pfos_number", sa.String(), nullable=True),
        sa.Column("board_type", sa.String(), nullable=True),
        sa.Column("pi_person_id", sa.String(), nullable=True),
        sa.Column("pi_first_name", sa.String(), nullable=True),
        sa.Column("pi_middle_name", sa.String(), nullable=True),
        sa.Column("pi_last_name", sa.String(), nullable=True),
        sa.Column("pi_email", sa.String(), nullable=True),
        sa.Column("pi_organization", sa.String(), nullable=True),
        sa.Column("pi_org_code", sa.String(), nullable=True),
        sa.Column("pi_department", sa.String(), nullable=True),
        sa.Column("pi_business_phone_number", sa.String(), nullable=True),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("cpu_allocated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("gpu_allocated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("kubernetes_namespace", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_aime_allocation_id"), "projects", ["aime_allocation_id"], unique=True)
    op.create_index(op.f("ix_projects_allocation_record_id"), "projects", ["allocation_record_id"], unique=True)
    op.create_index(op.f("ix_projects_grant_number"), "projects", ["grant_number"], unique=True)
    op.create_index(op.f("ix_projects_site_project_id"), "projects", ["site_project_id"], unique=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("middle_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("person_id", sa.String(), nullable=True),
        sa.Column("global_id", sa.String(), nullable=True),
        sa.Column("organization", sa.String(), nullable=True),
        sa.Column("org_code", sa.String(), nullable=True),
        sa.Column("remote_site_login", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_person_id"), "users", ["person_id"], unique=True)

    op.create_table(
        "project_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("remote_site_login", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "user_id", "resource", name="uq_project_user_resource"
        ),
    )

    op.create_table(
        "amie_allocation_packets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("packet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grant_number", sa.String(), nullable=False),
        sa.Column("record_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("allocation_type", sa.String(), nullable=False),
        sa.Column("request_type", sa.String(), nullable=True),
        sa.Column("service_units_allocated", sa.String(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("project_title", sa.String(), nullable=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("board_type", sa.String(), nullable=True),
        sa.Column("pfos_number", sa.String(), nullable=False),
        sa.Column("pi_person_id", sa.String(), nullable=True),
        sa.Column("pi_first_name", sa.String(), nullable=False),
        sa.Column("pi_middle_name", sa.String(), nullable=True),
        sa.Column("pi_last_name", sa.String(), nullable=False),
        sa.Column("pi_email", sa.String(), nullable=True),
        sa.Column("pi_organization", sa.String(), nullable=False),
        sa.Column("pi_org_code", sa.String(), nullable=False),
        sa.Column("role_list", sa.JSON(), nullable=False),
        sa.Column("pi_dn_list", sa.JSON(), nullable=False),
        sa.Column("pi_requested_login_list", sa.JSON(), nullable=False),
        sa.Column("site_person_ids", sa.JSON(), nullable=False),
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
        op.f("ix_amie_allocation_packets_grant_number"),
        "amie_allocation_packets",
        ["grant_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_allocation_packets_project_id"),
        "amie_allocation_packets",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_allocation_packets_record_id"),
        "amie_allocation_packets",
        ["record_id"],
        unique=False,
    )

    op.create_table(
        "amie_new_user_packets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("packet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grant_number", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("resource", sa.String(), nullable=True),
        sa.Column("user_person_id", sa.String(), nullable=True),
        sa.Column("user_global_id", sa.String(), nullable=True),
        sa.Column("user_first_name", sa.String(), nullable=False),
        sa.Column("user_middle_name", sa.String(), nullable=True),
        sa.Column("user_last_name", sa.String(), nullable=False),
        sa.Column("user_organization", sa.String(), nullable=False),
        sa.Column("user_org_code", sa.String(), nullable=False),
        sa.Column("user_department", sa.String(), nullable=True),
        sa.Column("user_email", sa.String(), nullable=True),
        sa.Column("user_business_phone_number", sa.String(), nullable=True),
        sa.Column("user_remote_site_login", sa.String(), nullable=True),
        sa.Column("nsf_status_code", sa.String(), nullable=True),
        sa.Column("role_list", sa.JSON(), nullable=False),
        sa.Column("user_dn_list", sa.JSON(), nullable=False),
        sa.Column("user_requested_login_list", sa.JSON(), nullable=False),
        sa.Column("site_person_ids", sa.JSON(), nullable=False),
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
        op.f("ix_amie_new_user_packets_grant_number"),
        "amie_new_user_packets",
        ["grant_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_new_user_packets_project_id"),
        "amie_new_user_packets",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_new_user_packets_user_person_id"),
        "amie_new_user_packets",
        ["user_person_id"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(op.f("ix_amie_new_user_packets_user_person_id"), table_name="amie_new_user_packets")
    op.drop_index(op.f("ix_amie_new_user_packets_project_id"), table_name="amie_new_user_packets")
    op.drop_index(op.f("ix_amie_new_user_packets_grant_number"), table_name="amie_new_user_packets")
    op.drop_table("amie_new_user_packets")

    op.drop_index(op.f("ix_amie_allocation_packets_record_id"), table_name="amie_allocation_packets")
    op.drop_index(op.f("ix_amie_allocation_packets_project_id"), table_name="amie_allocation_packets")
    op.drop_index(op.f("ix_amie_allocation_packets_grant_number"), table_name="amie_allocation_packets")
    op.drop_table("amie_allocation_packets")

    op.drop_table("project_users")

    op.drop_index(op.f("ix_users_person_id"), table_name="users")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_projects_site_project_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_grant_number"), table_name="projects")
    op.drop_index(op.f("ix_projects_allocation_record_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_aime_allocation_id"), table_name="projects")
    op.drop_table("projects")

    op.drop_index(op.f("ix_amie_packets_trans_rec_id"), table_name="amie_packets")
    op.drop_index(op.f("ix_amie_packets_packet_type"), table_name="amie_packets")
    op.drop_index(op.f("ix_amie_packets_packet_rec_id"), table_name="amie_packets")
    op.drop_table("amie_packets")
