"""Store transaction identifiers for delayed reply workflows.

Revision ID: 0007_store_transaction_ids
Revises: 0006_proj_user_acct_life
Create Date: 2026-03-14 22:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0007_store_transaction_ids"
down_revision = "0006_proj_user_acct_life"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "projects",
        sa.Column("source_packet_rec_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("source_trans_rec_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("source_transaction_id", sa.BigInteger(), nullable=True),
    )

    op.create_index(
        op.f("ix_projects_source_packet_rec_id"),
        "projects",
        ["source_packet_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projects_source_trans_rec_id"),
        "projects",
        ["source_trans_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_projects_source_transaction_id"),
        "projects",
        ["source_transaction_id"],
        unique=False,
    )

    op.add_column(
        "project_users",
        sa.Column("source_trans_rec_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "project_users",
        sa.Column("source_transaction_id", sa.BigInteger(), nullable=True),
    )

    op.create_index(
        op.f("ix_project_users_source_trans_rec_id"),
        "project_users",
        ["source_trans_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_users_source_transaction_id"),
        "project_users",
        ["source_transaction_id"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(
        op.f("ix_project_users_source_transaction_id"),
        table_name="project_users",
    )
    op.drop_index(
        op.f("ix_project_users_source_trans_rec_id"),
        table_name="project_users",
    )
    op.drop_column("project_users", "source_transaction_id")
    op.drop_column("project_users", "source_trans_rec_id")

    op.drop_index(
        op.f("ix_projects_source_transaction_id"),
        table_name="projects",
    )
    op.drop_index(
        op.f("ix_projects_source_trans_rec_id"),
        table_name="projects",
    )
    op.drop_index(
        op.f("ix_projects_source_packet_rec_id"),
        table_name="projects",
    )
    op.drop_column("projects", "source_transaction_id")
    op.drop_column("projects", "source_trans_rec_id")
    op.drop_column("projects", "source_packet_rec_id")
