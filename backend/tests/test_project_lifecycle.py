"""Tests for the Project lifecycle state machine."""

import pytest

from app.models.project import Project


class TestProjectLifecycleStates:
    """Verify the Project.LIFECYCLE_STATES tuple and constants are consistent."""

    def test_all_states_listed(self):
        expected = {
            "received",
            "waiting_pi_account",
            "pending_provisioning",
            "provisioning",
            "provisioning_failed",
            "provisioned",
            "aime_notified",
            "active",
            "inactive",
        }
        assert set(Project.LIFECYCLE_STATES) == expected

    def test_every_state_has_transition_entry(self):
        for state in Project.LIFECYCLE_STATES:
            assert state in Project.LIFECYCLE_STATE_TRANSITIONS, (
                f"{state} missing from LIFECYCLE_STATE_TRANSITIONS"
            )

    def test_transition_targets_are_valid_states(self):
        for source, targets in Project.LIFECYCLE_STATE_TRANSITIONS.items():
            for target in targets:
                assert target in Project.LIFECYCLE_STATES, (
                    f"Transition {source} -> {target}: target is not a valid state"
                )

    def test_default_lifecycle_state(self, db, make_project):
        project = make_project(db)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_RECEIVED


class TestProjectLifecycleTransitions:
    """Verify valid and invalid transitions on the Project model."""

    def test_received_to_pending_provisioning(self, db, make_project):
        project = make_project(db)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PENDING_PROVISIONING)
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PENDING_PROVISIONING)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_PENDING_PROVISIONING

    def test_received_cannot_skip_to_provisioning(self, db, make_project):
        project = make_project(db)
        assert not project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PROVISIONING)

    def test_received_cannot_go_to_waiting_pi(self, db, make_project):
        """waiting_pi_account comes after provisioning, not from received."""
        project = make_project(db)
        assert not project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT)

    def test_pending_provisioning_to_provisioning(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PENDING_PROVISIONING)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PROVISIONING)
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PROVISIONING)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_PROVISIONING

    def test_provisioning_to_provisioned(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONING)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PROVISIONED)

    def test_provisioning_to_failed(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONING)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PROVISIONING_FAILED)

    def test_provisioning_failed_can_retry(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONING_FAILED)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PROVISIONING)

    def test_provisioning_failed_cannot_skip_to_provisioned(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONING_FAILED)
        assert not project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PROVISIONED)

    def test_provisioned_to_waiting_pi_account(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONED)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT)

    def test_provisioned_to_aime_notified(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_PROVISIONED)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_AIME_NOTIFIED)

    def test_waiting_pi_account_to_provisioned(self, db, make_project):
        """After PI completes, project returns to provisioned for notification."""
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_PROVISIONED)

    def test_waiting_pi_account_cannot_skip_to_aime_notified(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT)
        assert not project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_AIME_NOTIFIED)

    def test_aime_notified_to_active(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_AIME_NOTIFIED)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_ACTIVE)

    def test_active_to_inactive(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_INACTIVE)

    def test_inactive_can_reactivate(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_INACTIVE)
        assert project.can_lifecycle_transition_to(Project.LIFECYCLE_STATE_ACTIVE)

    def test_terminal_aime_notified_cannot_go_backwards(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_AIME_NOTIFIED)
        for backward in (
            Project.LIFECYCLE_STATE_RECEIVED,
            Project.LIFECYCLE_STATE_PROVISIONING,
            Project.LIFECYCLE_STATE_PROVISIONED,
        ):
            assert not project.can_lifecycle_transition_to(backward), (
                f"aime_notified should not transition to {backward}"
            )


class TestProjectLifecycleHappyPaths:
    """Walk through the full lifecycle for PI and non-PI projects."""

    def test_non_pi_project_full_lifecycle(self, db, make_project):
        """received → pending_provisioning → provisioning → provisioned → aime_notified → active"""
        project = make_project(db)
        path = [
            Project.LIFECYCLE_STATE_PENDING_PROVISIONING,
            Project.LIFECYCLE_STATE_PROVISIONING,
            Project.LIFECYCLE_STATE_PROVISIONED,
            Project.LIFECYCLE_STATE_AIME_NOTIFIED,
            Project.LIFECYCLE_STATE_ACTIVE,
        ]
        for state in path:
            assert project.can_lifecycle_transition_to(state), (
                f"Cannot transition {project.lifecycle_state} → {state}"
            )
            project.set_lifecycle_state(state)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_ACTIVE

    def test_pi_project_full_lifecycle(self, db, make_project):
        """received → ... → provisioned → waiting_pi_account → provisioned → aime_notified → active"""
        project = make_project(db)
        path = [
            Project.LIFECYCLE_STATE_PENDING_PROVISIONING,
            Project.LIFECYCLE_STATE_PROVISIONING,
            Project.LIFECYCLE_STATE_PROVISIONED,
            Project.LIFECYCLE_STATE_WAITING_PI_ACCOUNT,
            Project.LIFECYCLE_STATE_PROVISIONED,  # PI done, back to provisioned
            Project.LIFECYCLE_STATE_AIME_NOTIFIED,
            Project.LIFECYCLE_STATE_ACTIVE,
        ]
        for state in path:
            assert project.can_lifecycle_transition_to(state), (
                f"Cannot transition {project.lifecycle_state} → {state}"
            )
            project.set_lifecycle_state(state)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_ACTIVE

    def test_provisioning_failure_and_retry(self, db, make_project):
        """received → ... → provisioning → failed → provisioning → provisioned"""
        project = make_project(db)
        path = [
            Project.LIFECYCLE_STATE_PENDING_PROVISIONING,
            Project.LIFECYCLE_STATE_PROVISIONING,
            Project.LIFECYCLE_STATE_PROVISIONING_FAILED,
            Project.LIFECYCLE_STATE_PROVISIONING,  # retry
            Project.LIFECYCLE_STATE_PROVISIONED,
        ]
        for state in path:
            assert project.can_lifecycle_transition_to(state)
            project.set_lifecycle_state(state)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_PROVISIONED

    def test_deactivation_and_reactivation(self, db, make_project):
        project = make_project(db, lifecycle_state=Project.LIFECYCLE_STATE_ACTIVE)
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_INACTIVE)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_INACTIVE
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_ACTIVE)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_ACTIVE


class TestSetLifecycleStateValidation:
    """Test set_lifecycle_state rejects unknown states."""

    def test_unknown_state_raises(self, db, make_project):
        project = make_project(db)
        with pytest.raises(ValueError, match="Unknown lifecycle state"):
            project.set_lifecycle_state("bogus_state")

    def test_empty_string_raises(self, db, make_project):
        project = make_project(db)
        with pytest.raises(ValueError, match="Unknown lifecycle state"):
            project.set_lifecycle_state("")

    def test_valid_state_does_not_raise(self, db, make_project):
        project = make_project(db)
        project.set_lifecycle_state(Project.LIFECYCLE_STATE_PENDING_PROVISIONING)
        assert project.lifecycle_state == Project.LIFECYCLE_STATE_PENDING_PROVISIONING
