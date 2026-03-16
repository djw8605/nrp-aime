"""Set default project-user state to not_sent_email_invite.

Revision ID: 0013_acct_state_invite
Revises: 0012_access_packet_fields
Create Date: 2026-03-16 15:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0013_acct_state_invite"
down_revision = "0012_access_packet_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.execute(
        "UPDATE project_users "
        "SET account_state = 'not_sent_email_invite' "
        "WHERE account_state = 'just_received_packet'"
    )
    op.alter_column(
        "project_users",
        "account_state",
        existing_type=sa.String(),
        server_default=sa.text("'not_sent_email_invite'"),
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.execute(
        "UPDATE project_users "
        "SET account_state = 'just_received_packet' "
        "WHERE account_state = 'not_sent_email_invite'"
    )
    op.alter_column(
        "project_users",
        "account_state",
        existing_type=sa.String(),
        server_default=sa.text("'just_received_packet'"),
    )
