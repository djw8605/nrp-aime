"""Tests for ACCESS packet lifecycle reply flows."""

from __future__ import annotations

import sys
import types
import unittest
from unittest.mock import patch

if "amieclient" not in sys.modules:
    amieclient_stub = types.ModuleType("amieclient")

    class _PlaceholderAMIEClient:  # pragma: no cover - import shim only
        def __init__(self, *args, **kwargs) -> None:  # noqa: D401, ANN002, ANN003
            raise AssertionError("Patch AMIEClient in tests before use")

    amieclient_stub.AMIEClient = _PlaceholderAMIEClient
    sys.modules["amieclient"] = amieclient_stub

import app.services.account_lifecycle as account_lifecycle
from app.models.outbound_packet_log import OutboundPacketLog
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.services.account_lifecycle import AccountLifecycleService
from app.services.aime.service import AIMEService
from tests.support import (
    FakeAMIEClient,
    FakeSourcePacket,
    TrackingAuthentikService,
    TrackingKubernetesService,
    TrackingProjectProvisioningService,
    create_test_session,
    data_account_create_packet,
    data_project_create_packet,
    request_account_create_packet,
    request_project_create_packet,
)


class AccountLifecycleTests(unittest.TestCase):
    """Validate outgoing lifecycle packet handling for ACCESS sequences."""

    def setUp(self) -> None:
        self.engine, self.db = create_test_session()
        self.authentik = TrackingAuthentikService()
        self.kubernetes = TrackingKubernetesService()
        self.provisioning = TrackingProjectProvisioningService()
        self.alert_patch = patch("app.services.aime.service.AlertService.send")
        self.alert_patch.start()
        self.service = AIMEService(
            site_name="NRP",
            authentik_service=self.authentik,
            kubernetes_service=self.kubernetes,
            project_provisioning_service=self.provisioning,
        )
        FakeAMIEClient.reset()
        self.patchers = [
            patch("app.services.account_lifecycle.AMIEClient", FakeAMIEClient),
            patch.object(account_lifecycle.settings, "amie_account_confirmation_enabled", True),
            patch.object(account_lifecycle.settings, "amie_api_key", "test-api-key"),
            patch.object(account_lifecycle.settings, "amie_site_name", "NRP"),
            patch.object(account_lifecycle.settings, "amie_site_names", "NRP"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.alert_patch.stop()
        self.db.close()
        self.engine.dispose()

    def test_reconcile_pending_project_notifications_sends_notify_project_create(self) -> None:
        source_packet = request_project_create_packet()
        self.service.ingest_packet(self.db, source_packet)

        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, role="pi", resource="cluster.example.org")
            .one()
        )
        membership.remote_site_login = "pi-login"
        membership.user.remote_site_login = "pi-login"
        project.lifecycle_state = Project.LIFECYCLE_STATE_PROVISIONED
        self.db.commit()

        lifecycle = AccountLifecycleService()
        self.assertFalse(lifecycle.account_confirmation_required(self.db, membership))

        FakeAMIEClient.source_packets[1001] = FakeSourcePacket(
            "request_project_create",
            source_packet["body"],
        )

        result = lifecycle.reconcile_pending_project_notifications(self.db)

        self.assertEqual(result["notifications_sent"], 1)
        self.assertEqual(result["failures"], 0)

        outbound = (
            self.db.query(OutboundPacketLog)
            .filter_by(event_type="notify_project_create", source_packet_rec_id=1001)
            .one()
        )
        self.db.refresh(membership)
        sent_packet = FakeAMIEClient.sent_packets[0]

        self.assertEqual(outbound.status, OutboundPacketLog.STATUS_SENT)
        self.assertIsNotNone(membership.aime_confirmation_sent_at)
        self.assertEqual(sent_packet.packet_type, "notify_project_create")
        self.assertEqual(sent_packet.GrantNumber, "TG-TEST123")
        self.assertEqual(sent_packet.ProjectID, "PROJECT-001")
        self.assertEqual(sent_packet.ResourceList, ["cluster.example.org"])
        self.assertEqual(sent_packet.PiPersonID, "PI-001")
        self.assertEqual(sent_packet.PiRemoteSiteLogin, "pi-login")
        self.assertEqual(
            sent_packet.SitePersonId,
            [{"PersonID": "pi-local", "Site": "X-PORTAL"}],
        )

    def test_reconcile_pending_confirmations_sends_notify_account_create(self) -> None:
        source_packet = request_account_create_packet()
        self.service.ingest_packet(self.db, source_packet)

        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        membership = (
            self.db.query(ProjectUser)
            .filter_by(project_id=project.id, resource="cluster.example.org")
            .one()
        )
        membership.remote_site_login = "member-login"
        membership.user.remote_site_login = "member-login"

        lifecycle = AccountLifecycleService()
        self.assertTrue(lifecycle.account_confirmation_required(self.db, membership))
        lifecycle.mark_email_sent(membership)
        lifecycle.mark_account_made(membership)
        self.db.commit()

        FakeAMIEClient.source_packets[2001] = FakeSourcePacket(
            "request_account_create",
            source_packet["body"],
        )

        with patch.object(
            lifecycle,
            "_invite_completion_allows_confirmation",
            return_value=True,
        ):
            result = lifecycle.reconcile_pending_confirmations(self.db)

        self.assertEqual(result["confirmations_sent"], 1)
        self.assertEqual(result["failures"], 0)

        outbound = (
            self.db.query(OutboundPacketLog)
            .filter_by(event_type="notify_account_create", source_packet_rec_id=2001)
            .one()
        )
        self.db.refresh(membership)
        sent_packet = FakeAMIEClient.sent_packets[0]

        self.assertEqual(outbound.status, OutboundPacketLog.STATUS_SENT)
        self.assertEqual(outbound.ack_status, OutboundPacketLog.ACK_ACKED)
        self.assertIsNotNone(membership.aime_confirmation_sent_at)
        self.assertEqual(sent_packet.packet_type, "notify_account_create")
        self.assertEqual(sent_packet.ProjectID, "PROJECT-001")
        self.assertEqual(sent_packet.ResourceList, ["cluster.example.org"])
        self.assertEqual(sent_packet.UserRemoteSiteLogin, "member-login")
        self.assertEqual(sent_packet.UserPersonID, "USER-2001")

    def _ingest_project_create_with_data_reply(self) -> Project:
        """Ingest an RPC + its data_project_create reply in one transaction."""
        rpc = request_project_create_packet()
        self.service.ingest_packet(self.db, rpc)

        dpc = data_project_create_packet()
        dpc["header"]["trans_rec_id"] = rpc["header"]["trans_rec_id"]
        self.service.ingest_packet(self.db, dpc)

        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        project.lifecycle_state = Project.LIFECYCLE_STATE_AIME_NOTIFIED
        self.db.commit()

        FakeAMIEClient.source_packets[3001] = FakeSourcePacket(
            "data_project_create",
            dpc["body"],
        )
        return project

    def test_reconcile_transaction_completions_sends_itc_and_activates_project(self) -> None:
        project = self._ingest_project_create_with_data_reply()

        lifecycle = AccountLifecycleService()
        result = lifecycle.reconcile_pending_transaction_completions(self.db)

        self.db.refresh(project)
        self.assertEqual(result["completions_sent"], 1)
        self.assertEqual(result["failures"], 0)

        sent_packet = FakeAMIEClient.sent_packets[0]
        self.assertEqual(sent_packet.packet_type, "inform_transaction_complete")
        self.assertEqual(sent_packet.StatusCode, "Success")

        outbound = (
            self.db.query(OutboundPacketLog)
            .filter_by(
                event_type="inform_transaction_complete",
                source_packet_rec_id=3001,
            )
            .one()
        )
        self.assertEqual(outbound.status, OutboundPacketLog.STATUS_SENT)
        self.assertEqual(project.lifecycle_state, Project.LIFECYCLE_STATE_ACTIVE)

    def test_reconcile_transaction_completions_is_idempotent(self) -> None:
        project = self._ingest_project_create_with_data_reply()

        lifecycle = AccountLifecycleService()
        first = lifecycle.reconcile_pending_transaction_completions(self.db)
        second = lifecycle.reconcile_pending_transaction_completions(self.db)

        self.db.refresh(project)
        self.assertEqual(first["completions_sent"], 1)
        self.assertEqual(second["completions_sent"], 0)
        self.assertEqual(second["already_sent"], 1)
        self.assertEqual(len(FakeAMIEClient.sent_packets), 1)
        self.assertEqual(project.lifecycle_state, Project.LIFECYCLE_STATE_ACTIVE)

    def test_reconcile_transaction_completions_tracks_failures_and_recovers(self) -> None:
        project = self._ingest_project_create_with_data_reply()

        FakeAMIEClient.send_failures = 1
        lifecycle = AccountLifecycleService()
        failed = lifecycle.reconcile_pending_transaction_completions(self.db)

        self.assertEqual(failed["failures"], 1)
        self.assertEqual(failed["completions_sent"], 0)
        outbound = (
            self.db.query(OutboundPacketLog)
            .filter_by(
                event_type="inform_transaction_complete",
                source_packet_rec_id=3001,
            )
            .one()
        )
        # The failure must be persisted with retry accounting on one row.
        self.assertEqual(outbound.status, OutboundPacketLog.STATUS_RETRYING)
        self.assertEqual(outbound.retry_count, 1)
        self.db.refresh(project)
        self.assertEqual(
            project.lifecycle_state,
            Project.LIFECYCLE_STATE_AIME_NOTIFIED,
        )

        # Next cycle resumes the same row and succeeds.
        recovered = lifecycle.reconcile_pending_transaction_completions(self.db)

        self.assertEqual(recovered["completions_sent"], 1)
        self.db.refresh(outbound)
        self.db.refresh(project)
        self.assertEqual(outbound.status, OutboundPacketLog.STATUS_SENT)
        self.assertEqual(
            self.db.query(OutboundPacketLog)
            .filter_by(event_type="inform_transaction_complete")
            .count(),
            1,
        )
        self.assertEqual(project.lifecycle_state, Project.LIFECYCLE_STATE_ACTIVE)

    def test_reconcile_transaction_completions_replies_to_data_account_create(self) -> None:
        rac = request_account_create_packet()
        self.service.ingest_packet(self.db, rac)

        dac = data_account_create_packet()
        dac["header"]["trans_rec_id"] = rac["header"]["trans_rec_id"]
        self.service.ingest_packet(self.db, dac)

        project = self.db.query(Project).filter_by(site_project_id="PROJECT-001").one()
        lifecycle_before = project.lifecycle_state

        FakeAMIEClient.source_packets[3101] = FakeSourcePacket(
            "data_account_create",
            dac["body"],
        )

        lifecycle = AccountLifecycleService()
        result = lifecycle.reconcile_pending_transaction_completions(self.db)

        self.db.refresh(project)
        self.assertEqual(result["completions_sent"], 1)
        self.assertEqual(result["failures"], 0)

        sent_packet = FakeAMIEClient.sent_packets[0]
        self.assertEqual(sent_packet.packet_type, "inform_transaction_complete")
        self.assertEqual(sent_packet.StatusCode, "Success")
        # Account-transaction completion must not touch the project lifecycle.
        self.assertEqual(project.lifecycle_state, lifecycle_before)


if __name__ == "__main__":
    unittest.main()
