"""Reset PI memberships wrongly seeded as account_made.

``request_project_create`` ingestion used to seed the PI's project membership
with the legacy ``account_made`` state before the PI ever onboarded.  That
made ``_has_pending_pi_account`` treat the PI as finished, so projects skipped
the ``waiting_pi_account`` gate and the frontend showed the PI account step as
complete.  Reset PI rows that show no onboarding evidence (no completion
timestamp and no remote site login) back to ``received``; the aime-worker
reconciler then moves the affected projects to ``waiting_pi_account``.

Revision ID: 0021_reset_unonboarded_pi_state
Revises: 0020_lifecycle_state_machine
Create Date: 2026-07-07 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0021_reset_unonboarded_pi_state"
down_revision = "0020_lifecycle_state_machine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE project_users
        SET account_state = 'received',
            account_state_updated_at = CURRENT_TIMESTAMP
        WHERE account_state = 'account_made'
          AND lower(role) = 'pi'
          AND account_made_at IS NULL
          AND (remote_site_login IS NULL OR remote_site_login = '')
        """
    )
    # Migration 0020 backfilled legacy 'account_made' rows to
    # 'user_completed_oauth' without stamping account_made_at.  The
    # application always stamps account_made_at when it sets
    # user_completed_oauth, so rows in that state with no completion
    # timestamp and no remote login can only be 0020 residue of the same
    # mis-seeding bug.
    op.execute(
        """
        UPDATE project_users
        SET account_state = 'received',
            account_state_updated_at = CURRENT_TIMESTAMP
        WHERE account_state = 'user_completed_oauth'
          AND lower(role) = 'pi'
          AND account_made_at IS NULL
          AND (remote_site_login IS NULL OR remote_site_login = '')
        """
    )


def downgrade() -> None:
    # Irreversible data repair: the pre-migration rows were incorrect and the
    # original values cannot be distinguished from legitimately completed
    # accounts, so downgrade intentionally leaves the corrected data in place.
    pass
