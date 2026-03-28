"""Add lifecycle state machine to projects and account state machine to project_users.

Introduces ``lifecycle_state`` on projects and migrates ``account_state``
on project_users to the new canonical state machine values.

Revision ID: 0020_lifecycle_state_machine
Revises: 0019_user_action_log
Create Date: 2026-03-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0020_lifecycle_state_machine"
down_revision = "0019_user_action_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- Project: add lifecycle_state column --------------------------------
    op.add_column(
        "projects",
        sa.Column(
            "lifecycle_state",
            sa.String(64),
            nullable=False,
            server_default="received",
        ),
    )
    op.create_index("ix_projects_lifecycle_state", "projects", ["lifecycle_state"])

    # Backfill lifecycle_state from existing provisioning_state values.
    # Mapping: received -> received, provisioning -> provisioning,
    # ready -> provisioned, failed -> provisioning_failed
    op.execute(
        """
        UPDATE projects SET lifecycle_state = CASE
            WHEN provisioning_state = 'received' THEN 'received'
            WHEN provisioning_state = 'provisioning' THEN 'provisioning'
            WHEN provisioning_state = 'ready' THEN 'provisioned'
            WHEN provisioning_state = 'failed' THEN 'provisioning_failed'
            ELSE 'received'
        END
        """
    )

    # -- ProjectUser: migrate account_state values --------------------------
    # Map old state names to new canonical names.
    op.execute(
        """
        UPDATE project_users SET account_state = CASE
            WHEN account_state IN ('not_sent_email_invite', 'just_received_packet')
                THEN 'received'
            WHEN account_state = 'sent_email'
                THEN 'email_invite_sent'
            WHEN account_state = 'account_made' AND aime_confirmation_sent_at IS NOT NULL
                THEN 'aime_notified'
            WHEN account_state = 'account_made'
                THEN 'user_completed_oauth'
            ELSE account_state
        END
        """
    )

    # Update the server default for account_state.
    op.alter_column(
        "project_users",
        "account_state",
        server_default="received",
    )


def downgrade() -> None:
    # -- ProjectUser: revert account_state values ---------------------------
    op.execute(
        """
        UPDATE project_users SET account_state = CASE
            WHEN account_state = 'received' THEN 'not_sent_email_invite'
            WHEN account_state = 'email_invite_sent' THEN 'sent_email'
            WHEN account_state IN ('user_completed_oauth', 'covered_by_project_notification')
                THEN 'account_made'
            WHEN account_state = 'aime_notified' THEN 'account_made'
            ELSE account_state
        END
        """
    )
    op.alter_column(
        "project_users",
        "account_state",
        server_default="not_sent_email_invite",
    )

    # -- Project: remove lifecycle_state ------------------------------------
    op.drop_index("ix_projects_lifecycle_state", table_name="projects")
    op.drop_column("projects", "lifecycle_state")
