"""Tests for invite callback finalization when namespace access fails."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.project import Project
from app.models.project_invite import ProjectInvite
from app.models.project_invite_event import ProjectInviteEvent
from app.models.project_user import ProjectUser
from app.services.invites.service import InviteFlowError, InviteService

AUTH_USERNAME = "http://cilogon.org/serverE/users/619283"


class _FakeAuthentik:
    def __init__(self, email: str) -> None:
        self.email = email

    def validate_callback(self, **_kwargs):
        return {"email": self.email, "username": AUTH_USERNAME, "name": "PI Person"}


class _FakeKubernetes:
    """Portal stand-in: namespaces listed in ``broken`` have no Authentik group."""

    def __init__(self, broken: set[str]) -> None:
        self.broken = broken
        self.calls: list[str] = []

    def ensure_user_project_access(self, *, project, user, project_user):  # noqa: ARG002
        namespace = project.kubernetes_namespace
        self.calls.append(namespace)
        if namespace in self.broken:
            return {
                "ok": False,
                "status": "rpc_error",
                "error": f"authentik group {namespace} does not exist yet",
                "namespace": namespace,
            }
        return {"ok": True, "namespace": namespace}


def _pi_project(db, make_project, namespace: str) -> Project:
    return make_project(
        db,
        kubernetes_namespace=namespace,
        authentik_group_name=namespace,
        lifecycle_state=Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT,
    )


def _invite(db, user) -> ProjectInvite:
    invite = ProjectInvite(
        email=user.email,
        token_hash=uuid.uuid4().hex,
        status=ProjectInvite.STATUS_PENDING,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        user_id=user.id,
        invite_metadata={},
    )
    db.add(invite)
    db.commit()
    return invite


@pytest.fixture()
def two_pi_projects(db, make_project, make_user, make_project_user):
    """PI with two projects; the first-created one has a broken Authentik group."""
    user = make_user(db, email="pi@example.edu")
    broken_project = _pi_project(db, make_project, "nrp-broken")
    good_project = _pi_project(db, make_project, "nrp-good")
    broken_pu = make_project_user(
        db,
        broken_project,
        user,
        role="pi",
        account_state=ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT,
        created_at=datetime.now(UTC) - timedelta(minutes=2),
    )
    good_pu = make_project_user(
        db,
        good_project,
        user,
        role="pi",
        account_state=ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT,
        created_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    invite = _invite(db, user)
    return {
        "user": user,
        "invite": invite,
        "broken_project": broken_project,
        "good_project": good_project,
        "broken_pu": broken_pu,
        "good_pu": good_pu,
    }


def _service(user_email: str, broken: set[str]) -> InviteService:
    svc = InviteService(
        authentik_service=_FakeAuthentik(user_email),
        email_service=object(),
        kubernetes_service=_FakeKubernetes(broken),
    )
    return svc


def _finalize(svc: InviteService, db, invite: ProjectInvite):
    svc._resolve_state_invite = lambda _db, *, state: invite  # noqa: ARG005
    return svc.finalize_callback(db, state="signed-state", code="auth-code")


class TestFinalizeCallbackPartialFailure:
    """One project's missing Authentik group must not affect the PI's other projects."""

    def test_failed_namespace_is_not_marked_onboarded(self, db, two_pi_projects):
        ctx = two_pi_projects
        svc = _service(ctx["user"].email, broken={"nrp-broken"})

        with pytest.raises(InviteFlowError) as excinfo:
            _finalize(svc, db, ctx["invite"])
        assert excinfo.value.code == "namespace_access_failed"

        # Simulate the API error path (records the failure and commits).
        svc.record_unbound_failure(
            db,
            event_type="invite_callback_failed",
            code=excinfo.value.code,
            message=excinfo.value.message,
        )
        db.expire_all()

        broken_pu = db.get(ProjectUser, ctx["broken_pu"].id)
        broken_project = db.get(Project, ctx["broken_project"].id)
        assert broken_pu.account_state == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT
        assert broken_pu.account_made_at is None
        assert broken_pu.remote_site_login is None
        assert broken_project.lifecycle_state == Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT

    def test_other_projects_still_complete_onboarding(self, db, two_pi_projects):
        ctx = two_pi_projects
        svc = _service(ctx["user"].email, broken={"nrp-broken"})

        with pytest.raises(InviteFlowError):
            _finalize(svc, db, ctx["invite"])
        svc.record_unbound_failure(
            db,
            event_type="invite_callback_failed",
            code="namespace_access_failed",
            message="Failed to assign namespace/group membership",
        )
        db.expire_all()

        assert svc.kubernetes_service.calls == ["nrp-broken", "nrp-good"]
        good_pu = db.get(ProjectUser, ctx["good_pu"].id)
        good_project = db.get(Project, ctx["good_project"].id)
        assert good_pu.account_state == ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH
        assert good_pu.account_made_at is not None
        assert good_pu.remote_site_login == AUTH_USERNAME
        assert good_project.lifecycle_state == Project.LIFECYCLE_STATE_PROVISIONED

    def test_invite_stays_pending_for_retry_and_failure_is_recorded(self, db, two_pi_projects):
        ctx = two_pi_projects
        svc = _service(ctx["user"].email, broken={"nrp-broken"})

        with pytest.raises(InviteFlowError):
            _finalize(svc, db, ctx["invite"])
        db.rollback()  # whatever the caller does, the failure record must already be saved
        db.expire_all()

        invite = db.get(ProjectInvite, ctx["invite"].id)
        assert invite.status == ProjectInvite.STATUS_PENDING
        events = (
            db.query(ProjectInviteEvent)
            .filter(
                ProjectInviteEvent.invite_id == invite.id,
                ProjectInviteEvent.event_type == "invite_namespace_access_failed",
            )
            .all()
        )
        assert len(events) == 1
        failed = events[0].event_payload["failed"]
        assert [row["namespace"] for row in failed] == ["nrp-broken"]
        assert "does not exist yet" in failed[0]["error"]

    def test_retry_after_group_fixed_completes_invite(self, db, two_pi_projects):
        ctx = two_pi_projects
        svc = _service(ctx["user"].email, broken={"nrp-broken"})
        with pytest.raises(InviteFlowError):
            _finalize(svc, db, ctx["invite"])

        svc.kubernetes_service.broken.clear()
        result = _finalize(svc, db, ctx["invite"])
        db.expire_all()

        assert result["status"] == ProjectInvite.STATUS_USED
        for key in ("broken_pu", "good_pu"):
            pu = db.get(ProjectUser, ctx[key].id)
            assert pu.account_state == ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH
        for key in ("broken_project", "good_project"):
            assert (
                db.get(Project, ctx[key].id).lifecycle_state
                == Project.LIFECYCLE_STATE_PROVISIONED
            )


class TestRecordUnboundFailure:
    """Recording a failure must not commit half-finished work from the failed request."""

    def test_discards_pending_changes(self, db, make_project, make_user, make_project_user):
        user = make_user(db)
        membership = make_project_user(
            db,
            make_project(db),
            user,
            account_state=ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT,
        )
        db.commit()

        membership.set_account_state(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
        InviteService(
            authentik_service=object(),
            email_service=object(),
            kubernetes_service=object(),
        ).record_unbound_failure(
            db,
            event_type="invite_callback_failed",
            code="boom",
            message="boom",
        )
        db.expire_all()

        assert (
            db.get(ProjectUser, membership.id).account_state
            == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT
        )
        assert (
            db.query(ProjectInviteEvent)
            .filter(ProjectInviteEvent.event_type == "invite_callback_failed")
            .count()
            == 1
        )
