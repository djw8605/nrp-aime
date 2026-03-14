"""Add project-user account lifecycle and confirmation tracking.

Revision ID: 0006_proj_user_acct_life
Revises: 0005_lifecycle_and_active_flags
Create Date: 2026-03-14 21:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_proj_user_acct_life"
down_revision = "0005_lifecycle_and_active_flags"
branch_labels = None
depends_on = None


ACCOUNT_STATE_JUST_RECEIVED_PACKET = "just_received_packet"


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "project_users",
        sa.Column(
            "account_state",
            sa.String(),
            nullable=False,
            server_default=sa.text(f"'{ACCOUNT_STATE_JUST_RECEIVED_PACKET}'"),
        ),
    )
    op.add_column(
        "project_users",
        sa.Column(
            "account_state_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "project_users",
        sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_users",
        sa.Column("account_made_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_users",
        sa.Column("aime_confirmation_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "project_users",
        sa.Column("source_packet_rec_id", sa.BigInteger(), nullable=True),
    )

    op.create_index(
        op.f("ix_project_users_account_state"),
        "project_users",
        ["account_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_users_source_packet_rec_id"),
        "project_users",
        ["source_packet_rec_id"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(
        op.f("ix_project_users_source_packet_rec_id"),
        table_name="project_users",
    )
    op.drop_index(
        op.f("ix_project_users_account_state"),
        table_name="project_users",
    )

    op.drop_column("project_users", "source_packet_rec_id")
    op.drop_column("project_users", "aime_confirmation_sent_at")
    op.drop_column("project_users", "account_made_at")
    op.drop_column("project_users", "email_sent_at")
    op.drop_column("project_users", "account_state_updated_at")
    op.drop_column("project_users", "account_state")
