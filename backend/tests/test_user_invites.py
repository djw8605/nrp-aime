"""Tests for person-centric invite behavior."""

import sys
import types

if "amieclient" not in sys.modules:
    amieclient_stub = types.ModuleType("amieclient")

    class _PlaceholderAMIEClient:  # pragma: no cover - import shim only
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
            raise AssertionError("Patch AMIEClient in tests before use")

    amieclient_stub.AMIEClient = _PlaceholderAMIEClient
    sys.modules["amieclient"] = amieclient_stub

from app.api.users import create_user_invite
from app.models.project_user import ProjectUser
from app.schemas.user import UserInviteCreate


class TestCreateUserInvite:
    """Verify invite creation advances membership lifecycle state."""

    def test_create_user_invite_marks_preinvite_memberships_sent(
        self,
        db,
        make_project,
        make_user,
        make_project_user,
    ):
        project = make_project(db)
        user = make_user(db)
        received_membership = make_project_user(
            db,
            project,
            user,
            account_state=ProjectUser.ACCOUNT_STATE_RECEIVED,
        )
        legacy_membership = make_project_user(
            db,
            make_project(db),
            user,
            account_state=ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE,
        )

        result = create_user_invite(
            user.id,
            UserInviteCreate(send_email=False),
            db,
        )

        db.refresh(received_membership)
        db.refresh(legacy_membership)

        assert result.user_id == user.id
        assert result.email_dispatched is False
        assert received_membership.account_state == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT
        assert legacy_membership.account_state == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT
        assert received_membership.email_sent_at is not None
        assert legacy_membership.email_sent_at is not None
