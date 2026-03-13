"""Authentik integration stub.

This module provides a placeholder for the future Authentik identity provider
integration.  Currently it only logs the requested action.
"""

import logging

logger = logging.getLogger(__name__)


def send_account_creation_email(project_id: str, user_email: str) -> None:
    """Send an account creation email via Authentik (stub).

    Args:
        project_id: The UUID of the project the user is being added to.
        user_email: The email address of the user.
    """
    logger.info(
        "STUB: send_account_creation_email called for project=%s user=%s",
        project_id,
        user_email,
    )
