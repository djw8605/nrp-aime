"""Helpers for detecting when the application database cannot accept writes."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# SQLSTATE 25006: read_only_sql_transaction (e.g. Postgres demoted to a standby).
_READ_ONLY_SQLSTATE = "25006"


def is_database_write_unavailable(exc: BaseException) -> bool:
    """Return True when ``exc`` means the database is read-only or unreachable."""
    if isinstance(exc, OperationalError):
        return True
    if isinstance(exc, DBAPIError):
        return getattr(exc.orig, "pgcode", None) == _READ_ONLY_SQLSTATE
    return False


def database_is_read_only(db: Session) -> bool:
    """Return True when the connected Postgres server is in recovery or read-only."""
    if db.get_bind().dialect.name != "postgresql":
        return False
    try:
        return bool(
            db.execute(
                text(
                    "SELECT pg_is_in_recovery() "
                    "OR current_setting('transaction_read_only') = 'on'"
                )
            ).scalar()
        )
    except SQLAlchemyError:
        logger.exception("Failed to check database read-only state")
        db.rollback()
        return False
