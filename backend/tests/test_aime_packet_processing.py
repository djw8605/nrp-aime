"""Tests for ACCESS packet ingestion behavior."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

from app.models.amie_allocation_packet import AMIEAllocationPacket
from app.models.amie_lifecycle_packet import AMIELifecyclePacket
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.amie_packet import AMIEPacket
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.aime.service import AIMEService
from tests.support import (
    TrackingAuthentikService,
    TrackingKubernetesService,
    TrackingProjectProvisioningService,
    create_test_session,
    data_account_create_packet,
    data_project_create_packet,
    inform_transaction_complete_packet,
    request_account_create_packet,
    request_account_inactivate_packet,
    request_account_reactivate_packet,
    request_project_create_packet,
    request_user_modify_packet,
)


class AIMEPacketProcessingTests(unittest.TestCase):
    """Validate packet ingestion against ACCESS transaction expectations."""

    def setUp(self) -> None:
        self.engine, self.db = create_test_session()
        self.authentik = TrackingAuthentikService()
        self.kubernetes = TrackingKubernetesService()
        self.provisioning = TrackingProjectProvisioningService()
        self.alert_patch = patch("app.services.aime.service.AlertService.send")
        self.mock_alert = self.alert_patch.start()
        self.service = AIMEService(
            site_name="NRP",
            authentik_service=self.authentik,
            kubernetes_service=self.kubernetes,
            project_provisioning_service=self.provisioning,
        )

    def tearDown(self) -> None:
        self.alert_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _make_project(
        self,
        *,
        active: bool = True,
        source_site_name: str = "ACCESS",
    ) -> Project:
        project = Project(
            aime_allocation_id="alloc-1",
            name="ACCESS Project",
            grant_number="TG-TEST123",
            site_project_id="PROJECT-001",
            project_title="ACCESS Project",
            source_site_name=source_site_name,
            resource_type="cluster.example.org",
            allocated_resource="cluster.example.org",
            is_active=active,
        )
        self.db.add(project)
        self.db.flush()
        return project

    def _make_user(
        self,
        *,
        person_id: str,
        email: str,
        name: str,
        source_site_name: str = "ACCESS",
        active: bool = True,
    ) -> User:
        user = User(
            person_id=person_id,
            email=email,
            name=name,
            source_site_name=source_site_name,
            is_active=active,
            dn_list=[],
        )
        self.db.add(user)
        self.db.flush()
        return user

    def test_request_project_create_reactivates_project_and_only_pi_membership(self) -> None:
        project = self._make_project(active=False)
        pi_user = self._make_user(
            person_id="PI-001",
            email="pi@example.org",
            name="Pat Investigator",
            active=False,
        )
        other_user = self._make_user(
            person_id="USER-OTHER",
            email="other@example.org",
            name="Other Member",
            active=False,
        )
        pi_membership = ProjectUser(
            project_id=project.id,
            user_id=pi_user.id,
            role="pi",
            resource="cluster.example.org",
            is_active=False,
            account_state=ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE,
            source_packet_rec_id=42,
        )
        other_membership = ProjectUser(
            project_id=project.id,
            user_id=other_user.id,
            role="member",
            resource="cluster.example.org",
            is_active=False,
            account_state=ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE,
            source_packet_rec_id=43,
        )
        self.db.add_all([pi_membership, other_membership])
        self.db.commit()

        result = self.service.ingest_packet(self.db, request_project_create_packet())

        self.assertTrue(result.handled)
        self.db.refresh(project)
        self.db.refresh(pi_user)
        self.db.refresh(pi_membership)
        self.db.refresh(other_membership)

        self.assertTrue(project.is_active)
        self.assertTrue(pi_user.is_active)
        self.assertTrue(pi_membership.is_active)
        self.assertEqual(
            pi_membership.account_state,
            ProjectUser.ACCOUNT_STATE_RECEIVED,
        )
        self.assertEqual(pi_membership.source_packet_rec_id, 1001)
        self.assertFalse(other_membership.is_active)
        self.assertEqual(
            self.db.query(AMIEAllocationPacket).count(),
            1,
        )

    def test_request_project_create_seeds_pi_membership_awaiting_onboarding(self) -> None:
        result = self.service.ingest_packet(self.db, request_project_create_packet())

        self.assertTrue(result.handled)
        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, role="pi")
            .one()
        )

        self.assertEqual(membership.account_state, ProjectUser.ACCOUNT_STATE_RECEIVED)
        self.assertIsNone(membership.account_made_at)
        self.assertEqual(project.source_packet_rec_id, 1001)

    def test_request_project_create_does_not_downgrade_onboarded_pi(self) -> None:
        self.service.ingest_packet(self.db, request_project_create_packet())
        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, role="pi")
            .one()
        )
        membership.set_account_state(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
        self.db.commit()

        # Re-delivery of the same packet must not reset onboarding progress.
        self.service.ingest_packet(self.db, request_project_create_packet())

        self.db.refresh(membership)
        self.assertEqual(
            membership.account_state,
            ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
        )

    def test_request_account_create_preserves_project_source_packet_linkage(self) -> None:
        self.service.ingest_packet(self.db, request_project_create_packet())
        self.service.ingest_packet(self.db, request_account_create_packet())

        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()

        # The notify_project_create reply is keyed off the project's source
        # packet; a later request_account_create must not clobber it.
        self.assertEqual(project.source_packet_rec_id, 1001)
        self.assertEqual(project.source_trans_rec_id, 2001)

    def test_request_account_create_creates_pending_membership_and_new_user_packet(self) -> None:
        result = self.service.ingest_packet(self.db, request_account_create_packet())

        self.assertTrue(result.handled)
        packet_record = self.db.query(AMIEPacket).filter_by(packet_rec_id=2001).one()
        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        user = self.db.query(User).filter_by(person_id="USER-2001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, user_id=user.id, resource="cluster.example.org")
            .one()
        )
        new_user_packet = self.db.query(AMIENewUserPacket).one()

        self.assertEqual(packet_record.processing_status, AMIEPacket.PROCESSING_STATUS_PROCESSED)
        self.assertEqual(membership.account_state, ProjectUser.ACCOUNT_STATE_JUST_RECEIVED_PACKET)
        self.assertTrue(membership.is_active)
        self.assertEqual(new_user_packet.user_person_id, "USER-2001")
        self.assertEqual(new_user_packet.project_id, "PROJECT-001")

    def test_data_account_create_does_not_downgrade_terminal_account_state(self) -> None:
        self.service.ingest_packet(self.db, request_account_create_packet())
        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        user = self.db.query(User).filter_by(person_id="USER-2001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, user_id=user.id)
            .one()
        )
        membership.set_account_state(ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED)
        self.db.commit()

        result = self.service.ingest_packet(self.db, data_account_create_packet())

        self.assertTrue(result.handled)
        self.db.refresh(membership)
        self.assertEqual(
            membership.account_state,
            ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
        )

    def test_data_account_create_advances_pre_oauth_account_state(self) -> None:
        self.service.ingest_packet(self.db, request_account_create_packet())
        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        user = self.db.query(User).filter_by(person_id="USER-2001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, user_id=user.id)
            .one()
        )
        membership.set_account_state(ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT)
        self.db.commit()

        result = self.service.ingest_packet(self.db, data_account_create_packet())

        self.assertTrue(result.handled)
        self.db.refresh(membership)
        self.assertEqual(
            membership.account_state,
            ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
        )

    def test_data_project_create_does_not_downgrade_covered_pi(self) -> None:
        self.service.ingest_packet(self.db, request_project_create_packet())
        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, role="pi")
            .one()
        )
        membership.set_account_state(
            ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT
        )
        self.db.commit()

        result = self.service.ingest_packet(self.db, data_project_create_packet())

        self.assertTrue(result.handled)
        self.db.refresh(membership)
        self.assertEqual(
            membership.account_state,
            ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT,
        )

    def test_request_account_inactivate_deactivates_membership_and_retains_user_record(self) -> None:
        project = self._make_project(active=True)
        user = self._make_user(
            person_id="USER-2001",
            email="member@example.org",
            name="Taylor Member",
        )
        membership = ProjectUser(
            project_id=project.id,
            user_id=user.id,
            role="member",
            resource="cluster.example.org",
            allocated_resource="cluster.example.org",
            is_active=True,
            account_state=ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE,
        )
        self.db.add(membership)
        self.db.commit()

        result = self.service.ingest_packet(self.db, request_account_inactivate_packet())

        self.assertTrue(result.handled)
        self.db.refresh(membership)
        self.db.refresh(user)
        lifecycle_packet = (
            self.db.query(AMIELifecyclePacket)
            .filter_by(packet_type="request_account_inactivate")
            .one()
        )

        self.assertFalse(membership.is_active)
        self.assertEqual(user.person_id, "USER-2001")
        self.assertEqual(lifecycle_packet.person_id, "USER-2001")
        self.assertEqual(len(self.authentik.remove_calls), 1)
        self.assertEqual(len(self.kubernetes.remove_calls), 1)

    def test_request_account_reactivate_reactivates_existing_membership(self) -> None:
        project = self._make_project(active=False)
        user = self._make_user(
            person_id="USER-2001",
            email="member@example.org",
            name="Taylor Member",
            active=False,
        )
        membership = ProjectUser(
            project_id=project.id,
            user_id=user.id,
            role="member",
            resource="cluster.example.org",
            allocated_resource="cluster.example.org",
            is_active=False,
            account_state=ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE,
        )
        self.db.add(membership)
        self.db.commit()

        result = self.service.ingest_packet(self.db, request_account_reactivate_packet())

        self.assertTrue(result.handled)
        self.db.refresh(project)
        self.db.refresh(user)
        self.db.refresh(membership)

        self.assertTrue(project.is_active)
        self.assertTrue(user.is_active)
        self.assertTrue(membership.is_active)
        self.assertEqual(
            membership.account_state,
            ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE,
        )
        self.assertEqual(len(self.authentik.ensure_calls), 1)
        self.assertEqual(len(self.kubernetes.ensure_calls), 1)

    def test_request_user_modify_replace_updates_user_fields_and_dn_list(self) -> None:
        user = self._make_user(
            person_id="USER-2001",
            email="member@example.org",
            name="Taylor Member",
        )
        user.first_name = "Taylor"
        user.last_name = "Member"
        user.organization = "Original University"
        user.org_code = "T111111"
        user.dn_list = ["/C=US/O=Example/CN=Old DN"]
        self.db.commit()

        result = self.service.ingest_packet(self.db, request_user_modify_packet())

        self.assertTrue(result.handled)
        self.db.refresh(user)
        lifecycle_packet = (
            self.db.query(AMIELifecyclePacket)
            .filter_by(packet_type="request_user_modify")
            .one()
        )

        self.assertEqual(user.name, "Taylor Member-Updated")
        self.assertEqual(user.email, "member-updated@example.org")
        self.assertEqual(user.organization, "Updated University")
        self.assertEqual(user.org_code, "T999999")
        self.assertEqual(user.dn_list, ["/C=US/O=Example/CN=Taylor Member Updated"])
        self.assertEqual(lifecycle_packet.action_type, "replace")

    def test_inform_transaction_complete_records_status_message_and_detail(self) -> None:
        result = self.service.ingest_packet(
            self.db,
            inform_transaction_complete_packet(
                Message="Project create complete",
                DetailCode=7,
                StatusCode="Success",
            ),
        )

        self.assertTrue(result.handled)
        lifecycle_packet = (
            self.db.query(AMIELifecyclePacket)
            .filter_by(packet_type="inform_transaction_complete")
            .one()
        )

        self.assertEqual(lifecycle_packet.status_code, "Success")
        self.assertEqual(lifecycle_packet.detail_code, "7")
        self.assertEqual(lifecycle_packet.message, "Project create complete")

    def test_duplicate_request_account_create_does_not_re_emit_alert(self) -> None:
        """Re-ingesting the same packet should not fire another user alert."""
        self.mock_alert.reset_mock()
        self.service.ingest_packet(self.db, request_account_create_packet())
        first_call_count = self.mock_alert.call_count

        # Re-ingest the same packet (same packet_rec_id)
        self.service.ingest_packet(self.db, request_account_create_packet())
        second_call_count = self.mock_alert.call_count

        self.assertGreater(first_call_count, 0, "First ingest should emit an alert")
        self.assertEqual(
            first_call_count,
            second_call_count,
            "Re-ingesting a duplicate packet should not emit another alert",
        )


class TestOutgoingFlagParsing(unittest.TestCase):
    """Verify outgoing_flag is correctly coerced from various AMIE formats."""

    def setUp(self) -> None:
        self.engine, self.db = create_test_session()
        self.alert_patch = patch("app.services.aime.service.AlertService.send")
        self.mock_alert = self.alert_patch.start()
        self.service = AIMEService(
            site_name="NRP",
            authentik_service=TrackingAuthentikService(),
            kubernetes_service=TrackingKubernetesService(),
            project_provisioning_service=TrackingProjectProvisioningService(),
        )

    def tearDown(self) -> None:
        self.alert_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _ingest_with_flag(self, outgoing_flag: Any, packet_rec_id: int) -> AMIEPacket:
        packet = request_project_create_packet(packet_rec_id=packet_rec_id)
        packet["header"]["outgoing_flag"] = outgoing_flag
        result = self.service.ingest_packet(self.db, packet)
        self.assertTrue(result.handled, f"Packet {packet_rec_id} was not handled")
        row = (
            self.db.query(AMIEPacket)
            .filter(AMIEPacket.packet_rec_id == packet_rec_id)
            .one()
        )
        self.assertEqual(row.processing_status, AMIEPacket.PROCESSING_STATUS_PROCESSED)
        return row

    def test_string_zero_is_not_outgoing(self) -> None:
        row = self._ingest_with_flag("0", 9001)
        self.assertFalse(row.outgoing_flag)

    def test_string_one_is_outgoing(self) -> None:
        row = self._ingest_with_flag("1", 9002)
        self.assertTrue(row.outgoing_flag)

    def test_string_false_is_not_outgoing(self) -> None:
        row = self._ingest_with_flag("false", 9003)
        self.assertFalse(row.outgoing_flag)

    def test_string_true_is_outgoing(self) -> None:
        row = self._ingest_with_flag("true", 9004)
        self.assertTrue(row.outgoing_flag)

    def test_bool_false_is_not_outgoing(self) -> None:
        row = self._ingest_with_flag(False, 9005)
        self.assertFalse(row.outgoing_flag)

    def test_bool_true_is_outgoing(self) -> None:
        row = self._ingest_with_flag(True, 9006)
        self.assertTrue(row.outgoing_flag)

    def test_none_is_none(self) -> None:
        row = self._ingest_with_flag(None, 9007)
        self.assertIsNone(row.outgoing_flag)

    def test_int_zero_is_not_outgoing(self) -> None:
        row = self._ingest_with_flag(0, 9008)
        self.assertFalse(row.outgoing_flag)

    def test_int_one_is_outgoing(self) -> None:
        row = self._ingest_with_flag(1, 9009)
        self.assertTrue(row.outgoing_flag)

    def test_string_yes_is_outgoing(self) -> None:
        row = self._ingest_with_flag("yes", 9010)
        self.assertTrue(row.outgoing_flag)


if __name__ == "__main__":
    unittest.main()
