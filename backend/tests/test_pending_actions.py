"""Tests for ObservabilityService.pending_actions."""

from app.models.project import Project
from app.models.project_user import ProjectUser
from app.services.observability import ObservabilityService


class TestPendingActionsEmpty:
    """Verify empty database returns zero counts."""

    def test_empty_database(self, db):
        result = ObservabilityService.pending_actions(db)
        assert result["total_pending_count"] == 0
        assert result["projects_pending_provisioning"] == []
        assert result["projects_provisioning_failed"] == []
        assert result["users_pending_email_invite"] == []
        assert result["users_pending_aime_notification"] == []


class TestPendingActionsProjectProvisioning:
    """Projects in received/pending_provisioning appear as pending."""

    def test_received_project_is_pending(self, db, make_project):
        make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_RECEIVED)
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["projects_pending_provisioning"]) == 1
        assert result["projects_pending_provisioning"][0]["lifecycle_state"] == "received"

    def test_pending_provisioning_project_is_pending(self, db, make_project):
        make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PENDING_PROVISIONING)
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["projects_pending_provisioning"]) == 1

    def test_active_project_not_pending(self, db, make_project):
        make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["projects_pending_provisioning"]) == 0

    def test_inactive_project_excluded(self, db, make_project):
        make_project(
            db,
            lifecycle_state=Project.LIFECYCLE_STATE_RECEIVED,
            is_active=False,
        )
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["projects_pending_provisioning"]) == 0


class TestPendingActionsProvisioningFailed:
    """Projects in provisioning_failed appear as failed."""

    def test_provisioning_failed_project(self, db, make_project):
        make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONING_FAILED)
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["projects_provisioning_failed"]) == 1
        assert result["projects_provisioning_failed"][0]["lifecycle_state"] == "provisioning_failed"


class TestPendingActionsUserEmailInvite:
    """ProjectUsers in received state need email invite."""

    def test_received_user_is_pending_email(self, db, make_project, make_user, make_project_user):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        user = make_user(db)
        make_project_user(
            db, project, user,
            account_state=ProjectUser.ACCOUNT_STATE_RECEIVED,
        )
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["users_pending_email_invite"]) == 1
        item = result["users_pending_email_invite"][0]
        assert item["user_name"] == user.name
        assert item["project_name"] == project.name

    def test_email_sent_user_not_pending(self, db, make_project, make_user, make_project_user):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        user = make_user(db)
        make_project_user(
            db, project, user,
            account_state=ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT,
        )
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["users_pending_email_invite"]) == 0


class TestPendingActionsUserAIMENotification:
    """ProjectUsers in user_completed_oauth state need AIME notification."""

    def test_oauth_completed_user_is_pending_aime(
        self, db, make_project, make_user, make_project_user,
    ):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        user = make_user(db)
        make_project_user(
            db, project, user,
            account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
        )
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["users_pending_aime_notification"]) == 1

    def test_aime_notified_user_not_pending(
        self, db, make_project, make_user, make_project_user,
    ):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        user = make_user(db)
        make_project_user(
            db, project, user,
            account_state=ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
        )
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert len(result["users_pending_aime_notification"]) == 0


class TestPendingActionsTotalCount:
    """Verify total_pending_count sums all categories."""

    def test_total_counts_all_categories(
        self, db, make_project, make_user, make_project_user,
    ):
        # 1 project pending provisioning
        make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_RECEIVED)
        # 1 project failed
        make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONING_FAILED)
        # 1 user pending email
        p = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        u1 = make_user(db)
        make_project_user(
            db, p, u1,
            account_state=ProjectUser.ACCOUNT_STATE_RECEIVED,
        )
        # 1 user pending AIME
        u2 = make_user(db)
        make_project_user(
            db, p, u2,
            account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
        )
        db.flush()
        result = ObservabilityService.pending_actions(db)
        assert result["total_pending_count"] == 4
