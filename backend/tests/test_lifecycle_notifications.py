"""Tests for notify_(project|account)_(in|re)activate reply packet flows.

Each incoming ``request_*_(in|re)activate`` packet requires a matching
``notify_*`` reply so the AMIE transaction can complete. These tests exercise
:meth:`AccountLifecycleService.reconcile_pending_lifecycle_notifications`.
"""

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
from app.models.amie_lifecycle_packet import AMIELifecyclePacket
from app.models.outbound_packet_log import OutboundPacketLog
from app.models.project import Project
from app.services.account_lifecycle import AccountLifecycleService
from app.services.aime.service import AIMEService
from tests.support import (
    FakeAMIEClient,
    FakeSourcePacket,
    TrackingAuthentikService,
    TrackingKubernetesService,
    TrackingProjectProvisioningService,
    create_test_session,
    request_account_create_packet,
    request_account_inactivate_packet,
    request_account_reactivate_packet,
    request_project_create_packet,
    request_project_inactivate_packet,
    request_project_reactivate_packet,
)


class LifecycleNotificationTests(unittest.TestCase):
    """Validate outgoing notify_* replies for inactivate/reactivate requests."""

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
            patch.object(
                account_lifecycle.settings, "amie_account_confirmation_enabled", True
            ),
            patch.object(account_lifecycle.settings, "amie_api_key", "test-api-key"),
            patch.object(account_lifecycle.settings, "amie_site_name", "NRP"),
            patch.object(account_lifecycle.settings, "amie_site_names", "NRP"),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.lifecycle = AccountLifecycleService()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.alert_patch.stop()
        self.db.close()
        self.engine.dispose()

    def _ingest_project(self) -> None:
        self.service.ingest_packet(self.db, request_project_create_packet())

    def _ingest_project_and_member(self) -> None:
        self.service.ingest_packet(self.db, request_project_create_packet())
        self.service.ingest_packet(self.db, request_account_create_packet())

    def _register_source(self, packet: dict) -> None:
        FakeAMIEClient.source_packets[packet["header"]["packet_rec_id"]] = (
            FakeSourcePacket(packet["type"], packet["body"])
        )

    # ------------------------------------------------------------------
    # Project-scoped replies
    # ------------------------------------------------------------------
    def test_reconcile_sends_notify_project_inactivate(self) -> None:
        self._ingest_project()
        packet = request_project_inactivate_packet()
        self.service.ingest_packet(self.db, packet)
        self._register_source(packet)

        result = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)

        self.assertEqual(result["notifications_sent"], 1)
        self.assertEqual(result["failures"], 0)

        outbound = (
            self.db.query(OutboundPacketLog)
            .filter_by(event_type="notify_project_inactivate", source_packet_rec_id=8001)
            .one()
        )
        self.assertEqual(outbound.status, OutboundPacketLog.STATUS_SENT)

        sent = FakeAMIEClient.sent_packets[-1]
        self.assertEqual(sent.packet_type, "notify_project_inactivate")
        self.assertEqual(sent.ProjectID, "PROJECT-001")
        self.assertEqual(sent.ResourceList, ["cluster.example.org"])

    def test_reconcile_sends_notify_project_reactivate(self) -> None:
        self._ingest_project()
        packet = request_project_reactivate_packet()
        self.service.ingest_packet(self.db, packet)
        self._register_source(packet)

        result = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)

        self.assertEqual(result["notifications_sent"], 1)
        self.assertEqual(result["failures"], 0)

        sent = FakeAMIEClient.sent_packets[-1]
        self.assertEqual(sent.packet_type, "notify_project_reactivate")
        self.assertEqual(sent.ProjectID, "PROJECT-001")
        self.assertEqual(sent.ResourceList, ["cluster.example.org"])

    # ------------------------------------------------------------------
    # Account-scoped replies
    # ------------------------------------------------------------------
    def test_reconcile_sends_notify_account_inactivate(self) -> None:
        self._ingest_project_and_member()
        packet = request_account_inactivate_packet()
        self.service.ingest_packet(self.db, packet)
        self._register_source(packet)

        result = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)

        self.assertEqual(result["notifications_sent"], 1)
        self.assertEqual(result["failures"], 0)

        outbound = (
            self.db.query(OutboundPacketLog)
            .filter_by(event_type="notify_account_inactivate", source_packet_rec_id=4001)
            .one()
        )
        self.assertEqual(outbound.status, OutboundPacketLog.STATUS_SENT)

        sent = FakeAMIEClient.sent_packets[-1]
        self.assertEqual(sent.packet_type, "notify_account_inactivate")
        self.assertEqual(sent.ProjectID, "PROJECT-001")
        self.assertEqual(sent.ResourceList, ["cluster.example.org"])
        self.assertEqual(sent.PersonID, "USER-2001")

    def test_reconcile_sends_notify_account_reactivate(self) -> None:
        self._ingest_project_and_member()
        packet = request_account_reactivate_packet()
        self.service.ingest_packet(self.db, packet)
        self._register_source(packet)

        result = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)

        self.assertEqual(result["notifications_sent"], 1)
        self.assertEqual(result["failures"], 0)

        sent = FakeAMIEClient.sent_packets[-1]
        self.assertEqual(sent.packet_type, "notify_account_reactivate")
        self.assertEqual(sent.ProjectID, "PROJECT-001")
        self.assertEqual(sent.PersonID, "USER-2001")

    # ------------------------------------------------------------------
    # Idempotency + interaction with incoming notify_* handlers
    # ------------------------------------------------------------------
    def test_reconcile_is_idempotent_across_cycles(self) -> None:
        self._ingest_project()
        packet = request_project_inactivate_packet()
        self.service.ingest_packet(self.db, packet)
        self._register_source(packet)

        first = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)
        second = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)

        self.assertEqual(first["notifications_sent"], 1)
        self.assertEqual(second["notifications_sent"], 0)
        self.assertEqual(second["already_sent"], 1)
        self.assertEqual(len(FakeAMIEClient.sent_packets), 1)

    def test_ingesting_own_notify_packet_does_not_trigger_reply(self) -> None:
        """Re-ingesting our own outgoing notify_* echo must not send a reply."""
        self._ingest_project()
        echo = {
            "type": "notify_project_inactivate",
            "header": {
                **request_project_inactivate_packet()["header"],
                "packet_rec_id": 91001,
                "outgoing_flag": True,
            },
            "body": request_project_inactivate_packet()["body"],
        }
        self.service.ingest_packet(self.db, echo)

        # The echo is recorded as a lifecycle packet ...
        recorded = (
            self.db.query(AMIELifecyclePacket)
            .filter_by(packet_type="notify_project_inactivate")
            .one()
        )
        self.assertEqual(recorded.project_id, "PROJECT-001")

        # ... but never produces an outbound reply.
        result = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)
        self.assertEqual(result["notifications_sent"], 0)
        self.assertEqual(FakeAMIEClient.sent_packets, [])
        self.assertEqual(self.db.query(OutboundPacketLog).count(), 0)

    def test_reconcile_defers_when_api_key_missing(self) -> None:
        self._ingest_project()
        packet = request_project_inactivate_packet()
        self.service.ingest_packet(self.db, packet)
        self._register_source(packet)

        with patch.object(account_lifecycle.settings, "amie_api_key", ""):
            result = self.lifecycle.reconcile_pending_lifecycle_notifications(self.db)

        self.assertEqual(result["notifications_sent"], 0)
        self.assertEqual(result["checked"], 1)
        self.assertEqual(FakeAMIEClient.sent_packets, [])


if __name__ == "__main__":
    unittest.main()
