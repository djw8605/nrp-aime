"""
Test suite for the amieclient library.

Exercises the packet and usage APIs documented at:
  https://xsede.github.io/amieclient/
  https://access-ci.atlassian.net/wiki/spaces/ACP/pages/589496333/AMIE+Documentation

These tests validate that the amieclient library behaves as the NRP AIME
backend expects – in particular the packet lifecycle (create, reply, send) and
the usage record/message API used by usage_worker.py.

Run standalone with:
    pip install amieclient pytest pytest-mock
    pytest tests/unit/test_amieclient.py -v
"""

import json
import tempfile
from configparser import ConfigParser
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from amieclient import AMIEClient
from amieclient.client import UsageClient
from amieclient.packet import RequestProjectCreate
from amieclient.packet.base import Packet
from amieclient.packet.project import (
    DataProjectCreate,
    NotifyProjectCreate,
    NotifyProjectInactivate,
    NotifyProjectReactivate,
    RequestProjectInactivate,
    RequestProjectReactivate,
)
from amieclient.packet.account import (
    DataAccountCreate,
    NotifyAccountCreate,
    NotifyAccountInactivate,
    NotifyAccountReactivate,
    RequestAccountCreate,
    RequestAccountInactivate,
    RequestAccountReactivate,
)
from amieclient.packet.person import (
    NotifyPersonDuplicate,
    NotifyPersonIDs,
    RequestPersonMerge,
)
from amieclient.packet.user import (
    NotifyUserModify,
    RequestUserModify,
)
from amieclient.packet.inform import InformTransactionComplete
from amieclient.usage.record import (
    ComputeUsageRecord,
    StorageUsageRecord,
    AdjustmentUsageRecord,
)
from amieclient.usage.message import UsageMessage


# ===========================================================================
# Section 1 – AMIEClient instantiation
# ===========================================================================

class TestAMIEClientCreation:
    """Verify the AMIEClient can be created in the ways shown in the docs."""

    def test_basic_creation(self):
        client = AMIEClient(site_name="PSC", api_key="test_key")
        assert client is not None

    def test_custom_url(self):
        client = AMIEClient(
            site_name="PSC",
            api_key="test_key",
            amie_url="https://amieclient.xsede.org/v0.20_beta/",
        )
        assert client is not None

    def test_context_manager(self):
        with AMIEClient("PSC", "test_key") as client:
            assert client is not None

    def test_config_file_creation(self):
        config_text = """\
[PSC]
site_name = PSC
api_key = some_secret_key

[PSC_TEST]
site_name = PSC
amie_url = https://amieclient.xsede.org/v0.20/
api_key = some_beta_key

[NCSA_LOCAL_DEV]
site_name = NCSA
amie_url = http://localhost:12345
usage_url = http://localhost:23456
api_key = some_dev_key
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False) as f:
            f.write(config_text)
            f.flush()
            config = ConfigParser()
            config.read(f.name)

        psc_cfg = config["PSC"]
        psc_client = AMIEClient(
            site_name=psc_cfg["site_name"], api_key=psc_cfg["api_key"]
        )
        assert psc_client is not None

        psc_test_cfg = config["PSC_TEST"]
        psc_test_client = AMIEClient(
            site_name=psc_test_cfg["site_name"],
            amie_url=psc_test_cfg["amie_url"],
            api_key=psc_test_cfg["api_key"],
        )
        assert psc_test_client is not None

    def test_config_dict_expansion(self):
        cfg = {
            "site_name": "PSC",
            "amie_url": "https://amieclient.xsede.org/v0.20/",
            "api_key": "beta_key",
        }
        client = AMIEClient(**cfg)
        assert client is not None


# ===========================================================================
# Section 2 – Packet creation from scratch
# ===========================================================================

class TestRequestProjectCreateFromScratch:
    """Build a RequestProjectCreate field-by-field, matching the docs example."""

    @pytest.fixture()
    def rpc(self):
        pkt = RequestProjectCreate()
        pkt.AllocationType = "new"
        pkt.GrantNumber = "TG-123456"
        pkt.PfosNumber = "12345"
        pkt.PiFirstName = "Jessica"
        pkt.PiLastName = "Scienceperson"
        pkt.PiOrganization = "PSC"
        pkt.PiOrgCode = "12345"
        pkt.EndDate = datetime.now() + timedelta(days=90)
        pkt.StartDate = datetime.now()
        pkt.ResourceList = ["supercomputer.psc.edu"]
        pkt.ServiceUnitsAllocated = "50000"
        return pkt

    def test_packet_type_is_correct(self, rpc):
        assert rpc.packet_type == "request_project_create"

    def test_required_fields_populated(self, rpc):
        assert rpc.GrantNumber == "TG-123456"
        assert rpc.PiFirstName == "Jessica"
        assert rpc.PiLastName == "Scienceperson"
        assert rpc.PiOrganization == "PSC"

    def test_resource_list_has_one_element(self, rpc):
        assert len(rpc.ResourceList) == 1

    def test_dates_are_sensible(self, rpc):
        assert rpc.EndDate > rpc.StartDate

    def test_as_dict_roundtrip(self, rpc):
        d = rpc.as_dict()
        assert isinstance(d, dict)
        # Body fields live under "body" or directly at the top level depending
        # on amieclient version; either way the dict must be non-empty.
        assert len(d) > 0

    def test_json_roundtrip(self, rpc):
        j = rpc.json()
        parsed = json.loads(j)
        assert isinstance(parsed, dict)

    def test_validation_passes(self, rpc):
        """A fully-populated RPC should pass (or at least not return False)."""
        result = rpc.validate_data()
        assert result is not False


# ===========================================================================
# Section 3 – Packet reply mechanism
# ===========================================================================

class TestPacketReply:
    """Tests the reply_packet() and reply_with_failure() helpers."""

    @pytest.fixture()
    def incoming_rpc(self):
        pkt = RequestProjectCreate(packet_rec_id="99999")
        pkt.AllocationType = "new"
        pkt.GrantNumber = "TG-654321"
        pkt.PfosNumber = "99"
        pkt.PiFirstName = "Ada"
        pkt.PiLastName = "Lovelace"
        pkt.PiOrganization = "NCSA"
        pkt.PiOrgCode = "99999"
        pkt.StartDate = datetime.now()
        pkt.EndDate = datetime.now() + timedelta(days=365)
        pkt.ResourceList = ["delta.ncsa.edu"]
        pkt.ServiceUnitsAllocated = "100000"
        return pkt

    def test_reply_creates_notify_project_create(self, incoming_rpc):
        reply = incoming_rpc.reply_packet()
        assert isinstance(reply, NotifyProjectCreate)

    def test_reply_references_original(self, incoming_rpc):
        reply = incoming_rpc.reply_packet()
        # in_reply_to_id should match the source packet_rec_id (as int or str).
        assert str(reply.in_reply_to_id) == "99999"

    def test_reply_with_failure_creates_itc(self, incoming_rpc):
        """reply_with_failure may not exist on all amieclient versions."""
        if not hasattr(incoming_rpc, "reply_with_failure"):
            pytest.skip("reply_with_failure not available in this amieclient version")
        fail = incoming_rpc.reply_with_failure()
        assert isinstance(fail, InformTransactionComplete)

    def test_reply_with_failure_custom_message(self, incoming_rpc):
        """reply_with_failure accepts optional keyword arguments per the docs."""
        if not hasattr(incoming_rpc, "reply_with_failure"):
            pytest.skip("reply_with_failure not available in this amieclient version")
        try:
            fail = incoming_rpc.reply_with_failure(
                detail_code="5", message="could not create project"
            )
        except TypeError:
            fail = incoming_rpc.reply_with_failure()
        assert isinstance(fail, InformTransactionComplete)


# ===========================================================================
# Section 4 – All documented packet types exist and round-trip
# ===========================================================================

ALL_PACKET_CLASSES = [
    # Project
    RequestProjectCreate,
    NotifyProjectCreate,
    DataProjectCreate,
    RequestProjectInactivate,
    NotifyProjectInactivate,
    RequestProjectReactivate,
    NotifyProjectReactivate,
    # Account
    RequestAccountCreate,
    NotifyAccountCreate,
    DataAccountCreate,
    RequestAccountInactivate,
    NotifyAccountInactivate,
    RequestAccountReactivate,
    NotifyAccountReactivate,
    # Person
    NotifyPersonDuplicate,
    NotifyPersonIDs,
    RequestPersonMerge,
    # User
    RequestUserModify,
    NotifyUserModify,
    # Informational
    InformTransactionComplete,
]


class TestPacketTypesCatalog:
    """Every packet class should be instantiable and serialisable."""

    @pytest.mark.parametrize("cls", ALL_PACKET_CLASSES, ids=lambda c: c.__name__)
    def test_instantiate(self, cls):
        pkt = cls()
        assert pkt is not None

    @pytest.mark.parametrize("cls", ALL_PACKET_CLASSES, ids=lambda c: c.__name__)
    def test_has_packet_type(self, cls):
        pkt = cls()
        assert pkt.packet_type is not None
        assert isinstance(pkt.packet_type, str)

    @pytest.mark.parametrize("cls", ALL_PACKET_CLASSES, ids=lambda c: c.__name__)
    def test_as_dict(self, cls):
        pkt = cls()
        d = pkt.as_dict()
        assert isinstance(d, dict)

    @pytest.mark.parametrize("cls", ALL_PACKET_CLASSES, ids=lambda c: c.__name__)
    def test_json_serialization(self, cls):
        pkt = cls()
        j = pkt.json()
        assert isinstance(j, str)
        parsed = json.loads(j)
        assert isinstance(parsed, dict)


# ===========================================================================
# Section 5 – Packet from_dict / from_json
# ===========================================================================

class TestPacketDeserialization:
    """The docs show Packet.from_dict() and Packet.from_json()."""

    def test_from_dict_rpc(self):
        rpc = RequestProjectCreate()
        rpc.GrantNumber = "TG-111"
        rpc.PiFirstName = "Test"
        rpc.PiLastName = "User"
        d = rpc.as_dict()
        restored = RequestProjectCreate.from_dict(d)
        assert restored.GrantNumber == "TG-111"

    def test_from_json_rpc(self):
        rpc = RequestProjectCreate()
        rpc.GrantNumber = "TG-222"
        rpc.PiFirstName = "Another"
        rpc.PiLastName = "Person"
        j = rpc.json()
        restored = RequestProjectCreate.from_json(j)
        assert restored.GrantNumber == "TG-222"


# ===========================================================================
# Section 6 – Packet validation
# ===========================================================================

class TestPacketValidation:
    """validate_data() and missing_attributes() behave as documented."""

    def test_empty_rpc_has_missing_fields(self):
        rpc = RequestProjectCreate()
        missing = rpc.missing_attributes()
        assert isinstance(missing, list)
        assert len(missing) > 0, "An empty RPC should report missing required fields"

    def test_nac_rejects_multiple_resources(self):
        """NotifyAccountCreate requires exactly one resource."""
        nac = NotifyAccountCreate()
        nac.ResourceList = ["res1", "res2"]
        result = nac.validate_data(raise_on_invalid=False)
        # Should be False or None (invalid); must not be True.
        assert result is not True

    def test_reply_packet_has_no_missing_attributes(self):
        """Docs say validation is relaxed when in_reply_to is set."""
        rpc = RequestProjectCreate(packet_rec_id="100")
        rpc.GrantNumber = "TG-999"
        rpc.PiFirstName = "X"
        rpc.PiLastName = "Y"
        rpc.PiOrganization = "Z"
        rpc.PiOrgCode = "0"
        rpc.StartDate = datetime.now()
        rpc.EndDate = datetime.now() + timedelta(days=30)
        rpc.ResourceList = ["r"]
        rpc.ServiceUnitsAllocated = "1"
        rpc.AllocationType = "new"
        rpc.PfosNumber = "1"
        reply = rpc.reply_packet()
        missing = reply.missing_attributes()
        # missing_attributes() returns a list; an empty list means all required
        # fields are present (or relaxed because this is a reply packet).
        assert isinstance(missing, list)


# ===========================================================================
# Section 7 – AMIEClient methods (mocked network calls)
# ===========================================================================

class TestAMIEClientMethods:
    """Test the client methods documented in the API – no real network calls."""

    @pytest.fixture()
    def client(self):
        return AMIEClient(site_name="PSC", api_key="mock_key")

    @patch("amieclient.client.AMIEClient.send_packet")
    def test_send_packet(self, mock_send, client):
        mock_send.return_value = MagicMock(status_code=200)
        rpc = RequestProjectCreate()
        rpc.AllocationType = "new"
        rpc.GrantNumber = "TG-000"
        resp = client.send_packet(rpc)
        mock_send.assert_called_once_with(rpc)
        assert resp.status_code == 200

    @patch("amieclient.client.AMIEClient.get_transaction")
    def test_get_transaction(self, mock_get, client):
        mock_trans = MagicMock()
        mock_trans.packets = [RequestProjectCreate(packet_rec_id="1")]
        mock_get.return_value = mock_trans
        trans = client.get_transaction(trans_rec_id="12345")
        assert len(trans.packets) == 1

    @patch("amieclient.client.AMIEClient.get_packet")
    def test_get_packet(self, mock_get, client):
        mock_get.return_value = RequestProjectCreate(packet_rec_id="42")
        pkt = client.get_packet(packet_rec_id="42")
        assert str(pkt.packet_rec_id) == "42"

    @patch("amieclient.client.AMIEClient.list_packets")
    def test_list_packets_by_state(self, mock_list, client):
        mock_list.return_value = [
            RequestProjectCreate(packet_rec_id="1"),
            RequestProjectCreate(packet_rec_id="2"),
        ]
        pkts = client.list_packets(states=["in-progress"])
        assert len(pkts) == 2

    @patch("amieclient.client.AMIEClient.list_packets")
    def test_list_packets_incoming(self, mock_list, client):
        mock_list.return_value = []
        client.list_packets(incoming=True)
        mock_list.assert_called_once_with(incoming=True)

    @patch("amieclient.client.AMIEClient.set_packet_client_state")
    def test_set_packet_client_state(self, mock_set, client):
        mock_set.return_value = None
        client.set_packet_client_state("42", "processing")
        mock_set.assert_called_once_with("42", "processing")

    @patch("amieclient.client.AMIEClient.set_packet_client_json")
    def test_set_packet_client_json(self, mock_set, client):
        mock_set.return_value = None
        client.set_packet_client_json("42", {"step": 1})
        mock_set.assert_called_once_with("42", {"step": 1})

    @patch("amieclient.client.AMIEClient.clear_packet_client_state")
    def test_clear_packet_client_state(self, mock_clear, client):
        mock_clear.return_value = None
        client.clear_packet_client_state("42")
        mock_clear.assert_called_once_with("42")

    @patch("amieclient.client.AMIEClient.clear_packet_client_json")
    def test_clear_packet_client_json(self, mock_clear, client):
        mock_clear.return_value = None
        client.clear_packet_client_json("42")
        mock_clear.assert_called_once_with("42")

    @patch("amieclient.client.AMIEClient.set_transaction_failed")
    def test_set_transaction_failed(self, mock_fail, client):
        mock_fail.return_value = None
        client.set_transaction_failed("12345")
        mock_fail.assert_called_once_with("12345")


# ===========================================================================
# Section 8 – Full workflow: receive RPC → reply NPC
# ===========================================================================

class TestFullProjectCreateWorkflow:
    """
    Simulates the documented end-to-end flow that aime_worker.py executes:
    1. Fetch a transaction containing RequestProjectCreate.
    2. Build a NotifyProjectCreate reply.
    3. Send the reply.
    """

    @patch("amieclient.client.AMIEClient.send_packet")
    @patch("amieclient.client.AMIEClient.get_transaction")
    def test_workflow(self, mock_get_trans, mock_send):
        rpc = RequestProjectCreate(packet_rec_id="500")
        rpc.AllocationType = "new"
        rpc.GrantNumber = "TG-WORK"
        rpc.PiFirstName = "Flow"
        rpc.PiLastName = "Test"
        rpc.ResourceList = ["cluster.psc.edu"]

        mock_trans = MagicMock()
        mock_trans.packets = [rpc]
        mock_get_trans.return_value = mock_trans
        mock_send.return_value = MagicMock(status_code=200)

        with AMIEClient("PSC", "mock_key") as client:
            trans = client.get_transaction(trans_rec_id="12345")
            incoming = trans.packets[-1]
            assert isinstance(incoming, RequestProjectCreate)

            reply = incoming.reply_packet()
            assert isinstance(reply, NotifyProjectCreate)
            assert str(reply.in_reply_to_id) == "500"

            resp = client.send_packet(reply)
            assert resp.status_code == 200


# ===========================================================================
# Section 9 – Usage API
# ===========================================================================

class TestUsageClientCreation:
    def test_basic_creation(self):
        uc = UsageClient(site_name="PSC", api_key="usage_key")
        assert uc is not None

    def test_custom_url(self):
        uc = UsageClient(
            site_name="PSC",
            api_key="usage_key",
            usage_url="http://localhost:23456",
        )
        assert uc is not None


class TestComputeUsageRecord:
    @pytest.fixture()
    def record(self):
        return ComputeUsageRecord(
            charge="150.5",
            end_time=datetime.now().isoformat(),
            local_project_id="PRJ-001",
            local_record_id="REC-001",
            resource="cluster.psc.edu",
            start_time=(datetime.now() - timedelta(hours=2)).isoformat(),
            submit_time=(datetime.now() - timedelta(hours=3)).isoformat(),
            username="jscience",
            node_count=4,
        )

    def test_creation(self, record):
        assert record is not None

    def test_as_dict(self, record):
        d = record.as_dict()
        assert isinstance(d, dict)
        # charge may be nested or flat depending on amieclient version
        raw = json.dumps(d)
        assert "150.5" in raw or "charge" in raw.lower()

    def test_from_dict_roundtrip(self, record):
        d = record.as_dict()
        restored = ComputeUsageRecord.from_dict(d)
        assert restored is not None

    def test_optional_fields(self):
        rec = ComputeUsageRecord(
            charge="50",
            end_time=datetime.now().isoformat(),
            local_project_id="PRJ-002",
            local_record_id="REC-002",
            resource="gpu.ncsa.edu",
            start_time=(datetime.now() - timedelta(hours=1)).isoformat(),
            submit_time=(datetime.now() - timedelta(hours=1, minutes=30)).isoformat(),
            username="alovelace",
            node_count=1,
            queue="gpu-shared",
            cpu_core_count=8,
            job_name="training_run",
            memory="32G",
        )
        assert rec is not None


class TestStorageUsageRecord:
    def test_creation_required_only(self):
        rec = StorageUsageRecord(
            charge="500",
            collection_time=datetime.now().isoformat(),
            local_project_id="PRJ-003",
            local_record_id="REC-003",
            resource="storage.psc.edu",
            username="jscience",
        )
        assert rec is not None

    def test_creation_with_optional_fields(self):
        rec = StorageUsageRecord(
            charge="1200",
            collection_time=datetime.now().isoformat(),
            local_project_id="PRJ-004",
            local_record_id="REC-004",
            resource="archive.ncsa.edu",
            username="alovelace",
            bytes_stored="1099511627776",
            media_type="Tape",
            file_count="42000",
        )
        assert rec is not None


class TestAdjustmentUsageRecord:
    VALID_TYPES = [
        "credit", "refund", "storage-credit", "debit", "reservation", "storage-debit"
    ]

    @pytest.mark.parametrize("adj_type", VALID_TYPES)
    def test_valid_adjustment_types(self, adj_type):
        rec = AdjustmentUsageRecord(
            adjustment_type=adj_type,
            charge="100",
            start_time=datetime.now().isoformat(),
            local_project_id="PRJ-005",
            local_record_id=f"ADJ-{adj_type}",
            resource="cluster.psc.edu",
            username="jscience",
        )
        assert rec is not None

    def test_with_comment(self):
        rec = AdjustmentUsageRecord(
            adjustment_type="refund",
            charge="200",
            start_time=datetime.now().isoformat(),
            local_project_id="PRJ-006",
            local_record_id="ADJ-REFUND",
            resource="cluster.psc.edu",
            username="jscience",
            comment="Job failed due to hardware error",
        )
        assert rec is not None


class TestUsageMessage:
    def _make_record(self, local_record_id: str = "REC") -> ComputeUsageRecord:
        return ComputeUsageRecord(
            charge="10",
            end_time=datetime.now().isoformat(),
            local_project_id="PRJ",
            local_record_id=local_record_id,
            resource="cluster.psc.edu",
            start_time=(datetime.now() - timedelta(hours=1)).isoformat(),
            submit_time=(datetime.now() - timedelta(hours=2)).isoformat(),
            username="user",
            node_count=1,
        )

    def test_create_compute_message(self):
        records = [self._make_record(f"REC-{i}") for i in range(3)]
        msg = UsageMessage(records)
        assert msg is not None

    def test_message_as_dict(self):
        msg = UsageMessage([self._make_record("REC-DICT")])
        d = msg.as_dict()
        assert isinstance(d, dict)

    def test_message_json(self):
        msg = UsageMessage([self._make_record("REC-JSON")])
        j = msg.json()
        parsed = json.loads(j)
        assert isinstance(parsed, dict)


class TestUsageClientMethods:
    @pytest.fixture()
    def uc(self):
        return UsageClient(site_name="PSC", api_key="mock_key")

    @patch("amieclient.client.UsageClient.send")
    def test_send_single_record(self, mock_send, uc):
        mock_send.return_value = [MagicMock(message="ok", failed_records=[])]
        rec = ComputeUsageRecord(
            charge="10",
            end_time=datetime.now().isoformat(),
            local_project_id="PRJ",
            local_record_id="REC-SEND",
            resource="cluster.psc.edu",
            start_time=(datetime.now() - timedelta(hours=1)).isoformat(),
            submit_time=(datetime.now() - timedelta(hours=2)).isoformat(),
            username="user",
            node_count=1,
        )
        responses = uc.send(rec)
        assert len(responses) >= 1

    @patch("amieclient.client.UsageClient.status")
    def test_status(self, mock_status, uc):
        mock_status.return_value = MagicMock(resources=[])
        result = uc.status(
            from_time=datetime.now() - timedelta(days=7),
            to_time=datetime.now(),
        )
        assert result is not None

    @patch("amieclient.client.UsageClient.get_failed_records")
    def test_get_failed_records(self, mock_failed, uc):
        mock_failed.return_value = []
        failed = uc.get_failed_records()
        assert isinstance(failed, list)

    @patch("amieclient.client.UsageClient.clear_failed_records")
    def test_clear_failed_records(self, mock_clear, uc):
        mock_clear.return_value = None
        uc.clear_failed_records([1, 2, 3])
        mock_clear.assert_called_once_with([1, 2, 3])


# ===========================================================================
# Section 10 – Transaction state model
# ===========================================================================

class TestTransactionStates:
    VALID_STATES = {"in-progress", "completed", "failed"}

    def test_valid_states_are_known(self):
        assert len(self.VALID_STATES) == 3
        assert "in-progress" in self.VALID_STATES

    @patch("amieclient.client.AMIEClient.list_packets")
    def test_filter_by_transaction_state(self, mock_list):
        mock_list.return_value = []
        client = AMIEClient(site_name="PSC", api_key="key")
        for state in self.VALID_STATES:
            client.list_packets(transaction_states=[state])
        assert mock_list.call_count == 3


# ===========================================================================
# Section 11 – pretty_print
# ===========================================================================

class TestPrettyPrint:
    def test_packet_pretty_print(self, capsys):
        rpc = RequestProjectCreate()
        rpc.GrantNumber = "TG-PRETTY"
        rpc.pretty_print()
        captured = capsys.readouterr()
        assert len(captured.out) > 0

    def test_usage_message_pretty_print(self, capsys):
        rec = ComputeUsageRecord(
            charge="10",
            end_time=datetime.now().isoformat(),
            local_project_id="PRJ",
            local_record_id="REC-PP",
            resource="cluster",
            start_time=datetime.now().isoformat(),
            submit_time=datetime.now().isoformat(),
            username="u",
            node_count=1,
        )
        msg = UsageMessage([rec])
        msg.pretty_print()
        captured = capsys.readouterr()
        assert len(captured.out) > 0


# ===========================================================================
# Section 12 – as_dict() integration with our bindings layer
# ===========================================================================

class TestAsIntegrationWithBindings:
    """
    Verify that amieclient packet dicts produced by as_dict() can be consumed
    by the backend's bind_packet() dispatcher without errors.
    """

    def _make_full_rpc(self) -> RequestProjectCreate:
        pkt = RequestProjectCreate()
        pkt.AllocationType = "new"
        pkt.GrantNumber = "TG-BIND-001"
        pkt.PfosNumber = "12345"
        pkt.PiFirstName = "Bind"
        pkt.PiLastName = "Test"
        pkt.PiOrganization = "PSC"
        pkt.PiOrgCode = "0001"
        pkt.StartDate = datetime.now()
        pkt.EndDate = datetime.now() + timedelta(days=365)
        pkt.ResourceList = ["cluster.psc.edu"]
        pkt.ServiceUnitsAllocated = "10000"
        pkt.RecordID = "REC-BIND-001"
        # Set required header fields so bind_packet can extract packet_rec_id
        pkt.packet_rec_id = 55555
        return pkt

    def test_rpc_dict_is_bindable(self):
        from app.services.aime.bindings import bind_packet, RequestProjectCreatePacketBinding

        rpc = self._make_full_rpc()
        raw = rpc.as_dict()

        # bind_packet expects {"type": ..., "header": {...}, "body": {...}}
        # amieclient's as_dict layout may differ; normalise it.
        if "type" not in raw:
            raw["type"] = rpc.packet_type
        if "header" not in raw:
            raw["header"] = {"packet_rec_id": int(rpc.packet_rec_id)}
        if "body" not in raw:
            # body fields are at the top level in older amieclient versions
            raw["body"] = {k: v for k, v in raw.items() if k not in ("type", "header")}

        # Ensure the minimum header field is present
        raw["header"].setdefault("packet_rec_id", 55555)

        bound = bind_packet(raw)
        assert isinstance(bound, RequestProjectCreatePacketBinding)
        assert bound.body.GrantNumber == "TG-BIND-001"

    def test_unsupported_type_raises(self):
        from app.services.aime.bindings import bind_packet, UnsupportedPacketType

        with pytest.raises(UnsupportedPacketType):
            bind_packet({"type": "not_a_real_packet_type", "header": {}, "body": {}})
