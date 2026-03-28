"""Tests for the ProjectUser account lifecycle state machine."""

import pytest

from app.models.project_user import ProjectUser


class TestAccountStates:
    """Verify the ACCOUNT_STATES tuple and constants are consistent."""

    def test_all_states_listed(self):
        expected = {
            "received",
            "email_invite_sent",
            "user_completed_oauth",
            "aime_notified",
            "covered_by_project_notification",
        }
        assert set(ProjectUser.ACCOUNT_STATES) == expected

    def test_every_state_has_transition_entry(self):
        for state in ProjectUser.ACCOUNT_STATES:
            assert state in ProjectUser.ACCOUNT_STATE_TRANSITIONS, (
                f"{state} missing from ACCOUNT_STATE_TRANSITIONS"
            )

    def test_transition_targets_are_valid_states(self):
        for source, targets in ProjectUser.ACCOUNT_STATE_TRANSITIONS.items():
            for target in targets:
                assert target in ProjectUser.ACCOUNT_STATES, (
                    f"Transition {source} -> {target}: target is not a valid state"
                )

    def test_every_state_has_rank(self):
        for state in ProjectUser.ACCOUNT_STATES:
            assert state in ProjectUser.ACCOUNT_STATE_RANK, (
                f"{state} missing from ACCOUNT_STATE_RANK"
            )

    def test_terminal_states_have_no_transitions(self):
        assert ProjectUser.ACCOUNT_STATE_TRANSITIONS[ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED] == set()
        assert ProjectUser.ACCOUNT_STATE_TRANSITIONS[ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT] == set()

    def test_default_account_state(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user)
        assert pu.account_state == ProjectUser.ACCOUNT_STATE_RECEIVED


class TestAccountStateTransitions:
    """Verify valid and invalid transitions on the ProjectUser model."""

    def test_received_to_email_invite_sent(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user)
        assert pu.can_transition_to(ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT)
        pu.set_account_state(ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT)
        assert pu.account_state == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT

    def test_received_cannot_skip_to_oauth(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user)
        assert not pu.can_transition_to(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)

    def test_email_invite_sent_to_oauth(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user, account_state=ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT)
        assert pu.can_transition_to(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)

    def test_oauth_to_aime_notified(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user, account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
        assert pu.can_transition_to(ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED)

    def test_oauth_to_covered_by_project(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user, account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
        assert pu.can_transition_to(ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT)

    def test_aime_notified_is_terminal(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user, account_state=ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED)
        for state in ProjectUser.ACCOUNT_STATES:
            assert not pu.can_transition_to(state), (
                f"aime_notified should not transition to {state}"
            )

    def test_covered_by_project_is_terminal(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user, account_state=ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT)
        for state in ProjectUser.ACCOUNT_STATES:
            assert not pu.can_transition_to(state), (
                f"covered_by_project should not transition to {state}"
            )


class TestAccountStateHappyPaths:
    """Walk through the full lifecycle for regular users and PIs."""

    def test_regular_user_full_lifecycle(self, db, make_project, make_user, make_project_user):
        """received → email_invite_sent → user_completed_oauth → aime_notified"""
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user)
        path = [
            ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT,
            ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
        ]
        for state in path:
            assert pu.can_transition_to(state), (
                f"Cannot transition {pu.account_state} → {state}"
            )
            pu.set_account_state(state)
        assert pu.account_state == ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED

    def test_pi_user_full_lifecycle(self, db, make_project, make_user, make_project_user):
        """received → email_invite_sent → user_completed_oauth → covered_by_project_notification"""
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user, role="PI")
        path = [
            ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT,
            ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT,
        ]
        for state in path:
            assert pu.can_transition_to(state), (
                f"Cannot transition {pu.account_state} → {state}"
            )
            pu.set_account_state(state)
        assert pu.account_state == ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT


class TestSetAccountStateValidation:
    """Test set_account_state rejects unknown states."""

    def test_unknown_state_raises(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user)
        with pytest.raises(ValueError, match="Unknown account state"):
            pu.set_account_state("bogus_state")

    def test_empty_string_raises(self, db, make_project, make_user, make_project_user):
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user)
        with pytest.raises(ValueError, match="Unknown account state"):
            pu.set_account_state("")

    def test_legacy_state_is_accepted(self, db, make_project, make_user, make_project_user):
        """Legacy values like 'account_made' are in ALL_ACCOUNT_STATES and should be accepted."""
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user)
        pu.set_account_state(ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE)
        assert pu.account_state == "account_made"

    def test_can_transition_to_returns_false_for_legacy_state(self, db, make_project, make_user, make_project_user):
        """Legacy states are not in ACCOUNT_STATE_TRANSITIONS, so can_transition_to returns False."""
        project = make_project(db)
        user = make_user(db)
        pu = make_project_user(db, project, user, account_state="account_made")
        assert not pu.can_transition_to(ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED)


class TestAccountStateRank:
    """Verify the rank ordering makes sense for monotonic progression."""

    def test_rank_increases_along_regular_path(self):
        path = [
            ProjectUser.ACCOUNT_STATE_RECEIVED,
            ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT,
            ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
        ]
        ranks = [ProjectUser.ACCOUNT_STATE_RANK[s] for s in path]
        assert ranks == sorted(ranks)
        assert len(set(ranks)) == len(ranks) or ranks[-1] == ranks[-2]  # last two may tie

    def test_terminal_states_share_max_rank(self):
        assert (
            ProjectUser.ACCOUNT_STATE_RANK[ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED]
            == ProjectUser.ACCOUNT_STATE_RANK[ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT]
        )
