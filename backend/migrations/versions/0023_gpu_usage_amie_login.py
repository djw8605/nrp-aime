"""Re-key GPU usage rows whose Username exceeds AMIE's 30-character login.

AMIE stores logins as varchar(30), so CILogon subject URLs are truncated to
their last 30 characters.  GPU usage was submitted with the full URL, which
ACCESS cannot map.  Re-key such rows to the 30-character login and reset them
to ``pending`` so they are re-sent.  ACCESS cannot have loaded records whose
Username does not exist in AMIE, so resetting (rather than zero-and-resend) is
safe.

Revision ID: 0023_gpu_usage_amie_login
Revises: 0022_gpu_usage_records
Create Date: 2026-10-08 12:00:00.000000
"""

import hashlib
from datetime import date

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0023_gpu_usage_amie_login"
down_revision = "0022_gpu_usage_records"
branch_labels = None
depends_on = None

AMIE_LOGIN_MAX_LENGTH = 30
REKEY_ERROR = "Re-keyed: Username exceeded the AMIE 30-character login limit"

# Same reset applied to a re-keyed row and to a row absorbing a merge.
_RESET_SQL = """
    status = 'pending',
    submitted_charge = NULL,
    submitted_at = NULL,
    loaded_at = NULL,
    accounting_db_record_id = NULL,
    last_error = :error,
    updated_at = CURRENT_TIMESTAMP
"""


def _amie_login(login: str) -> str:
    """Mirror of app.services.aime.logins.amie_login (no app imports here)."""
    return login.strip()[-AMIE_LOGIN_MAX_LENGTH:]


def _as_date(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def upgrade() -> None:
    """Re-key over-long GPU usage usernames and reset them to pending."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT r.id, r.project_id, r.usage_date, r.username, p.site_project_id "
            "FROM gpu_usage_records r "
            "JOIN projects p ON p.id = r.project_id "
            "WHERE length(r.username) > :limit"
        ),
        {"limit": AMIE_LOGIN_MAX_LENGTH},
    ).fetchall()

    for row_id, project_id, usage_date, username, site_project_id in rows:
        new_username = _amie_login(username)
        usage_day = _as_date(usage_date)
        digest = hashlib.sha256(new_username.encode()).hexdigest()[:12]
        local_record_id = f"nrp-gpu-{site_project_id}-{usage_day:%Y%m%d}-{digest}"

        existing = bind.execute(
            sa.text(
                "SELECT id FROM gpu_usage_records "
                "WHERE project_id = :project_id AND usage_date = :usage_date "
                "AND username = :username AND id <> :row_id"
            ),
            {
                "project_id": project_id,
                "usage_date": usage_date,
                "username": new_username,
                "row_id": row_id,
            },
        ).first()

        if existing is not None:
            # Merge the long-username row into the one already keyed correctly.
            bind.execute(
                sa.text(
                    "UPDATE gpu_usage_records SET "
                    "gpu_hours = gpu_hours + "
                    "(SELECT gpu_hours FROM gpu_usage_records WHERE id = :row_id), "
                    "charge = charge + "
                    "(SELECT charge FROM gpu_usage_records WHERE id = :row_id), "
                    + _RESET_SQL
                    + " WHERE id = :existing_id"
                ),
                {"row_id": row_id, "existing_id": existing[0], "error": REKEY_ERROR},
            )
            bind.execute(
                sa.text("DELETE FROM gpu_usage_records WHERE id = :row_id"),
                {"row_id": row_id},
            )
        else:
            bind.execute(
                sa.text(
                    "UPDATE gpu_usage_records SET "
                    "username = :username, local_record_id = :local_record_id, "
                    + _RESET_SQL
                    + " WHERE id = :row_id"
                ),
                {
                    "username": new_username,
                    "local_record_id": local_record_id,
                    "error": REKEY_ERROR,
                    "row_id": row_id,
                },
            )


def downgrade() -> None:
    """No-op: the re-key is a data change and is not reversible.

    The original over-long usernames are not retained, and ACCESS could not
    map them, so there is nothing meaningful to restore.
    """
