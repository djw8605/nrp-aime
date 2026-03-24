"""
Unit tests for app/services/account_lifecycle.py – AccountLifecycleService.

Covers state transitions, source-packet lookup logic, fallback login
resolution, idempotency of mark_account_made, confirmation packet sending
(with mocked AMIE client), and batch reconciliation.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.amie_packet import AMIEPacket
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.account_lifecycle import AccountLifecycleService


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def project(db):
    p = Project(
        aime_allocation_id="TG-TEST001",
        name="Test Project",
        grant_number="TG-TEST001",
        site_project_id="PROJ-001",
        source_site_name="XSEDE",
        cpu_allocated=0,
        gpu_allocated=0,
        is_active=True,
        tags=[],
    )
    db.add(p)
    db.flush()
    return p


@pytest.fixture
def user(db):
    u = User(
        email="ada@test.edu",
        name="Ada Lovelace",
        first_name="Ada",
        last_name="Lovelace",
        person_id="person-ada-001",
        organization="PSC",
        source_site_name="XSEDE",
        is_active=True,
        dn_list=[],
        tags=[],
    )
    db.add(u)
    db.flush()
    return u


@pytest.fixture
def project_user(db, project, user):
    pu = ProjectUser(
        project_id=project.id,
        user_id=user.id,
        resource="supercomputer.test.edu",
        is_active=True,
        account_state=ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE,
        account_state_updated_at=datetime.now(UTC),
    )
    db.add(pu)
    db.flush()
    return pu


@pytest.fixture
def source_packet(db, project):
    """A request_account_create AMIEPacket that project_user links to."""
    pkt = AMIEPacket(
        packet_rec_id=7001,
        trans_rec_id=8001,
        packet_type="request_account_create",
        local_site_name="NRP",
        remote_site_name="XSEDE",
        originating_site_name="XSEDE",
        processing_status=AMIEPacket.PROCESSING_STATUS_PROCESSED,
        ingest_source=AMIEPacket.INGEST_SOURCE_WORKER,
        raw_packet={"type": "request_account_create", "header": {}, "body": {}},
    )
    db.add(pkt)
    db.flush()
    return pkt


@pytest.fixture
def new_user_packet(db, source_packet, project, user):
    """AMIENewUserPacket linking the source packet to project+user."""
    nup = AMIENewUserPacket(
        packet_id=source_packet.id,
        grant_number="TG-TEST001",
        project_id="PROJ-001",
        user_person_id="person-ada-001",
        user_first_name="Ada",
        user_last_name="Lovelace",
        user_organization="PSC",
        user_org_code="99999",
        raw_body={},
    )
    db.add(nup)
    db.flush()
    return nup


@pytest.fixture
def svc():
    return AccountLifecycleService()


# ===========================================================================
# State transition methods
# ===========================================================================

class TestStateTransitions:
    def test_mark_just_received(self, project_user):
        AccountLifecycleService.mark_just_received(
            project_user, source_packet_rec_id=7001
        )
        assert project_user.account_state == ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE
        assert project_user.source_packet_rec_id == 7001

    def test_mark_just_received_without_packet_id(self, project_user):
        AccountLifecycleService.mark_just_received(project_user)
        assert project_user.account_state == ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE
        assert project_user.source_packet_rec_id is None

    def test_mark_email_sent(self, project_user):
        AccountLifecycleService.mark_email_sent(project_user)
        assert project_user.account_state == ProjectUser.ACCOUNT_STATE_SENT_EMAIL
        assert project_user.email_sent_at is not None

    def test_mark_account_made(self, project_user):
        AccountLifecycleService.mark_account_made(project_user)
        assert project_user.account_state == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE
        assert project_user.account_made_at is not None

    def test_mark_account_made_is_idempotent(self, project_user):
        """Calling mark_account_made twice must not overwrite account_made_at."""
        AccountLifecycleService.mark_account_made(project_user)
        first_ts = project_user.account_made_at

        AccountLifecycleService.mark_account_made(project_user)
        assert project_user.account_made_at == first_ts

    def test_set_account_state_rejects_invalid(self, project_user):
        with pytest.raises(ValueError, match="Unknown account state"):
            project_user.set_account_state("not_a_valid_state")


# ===========================================================================
# _fallback_login
# ===========================================================================

class TestFallbackLogin:
    def test_prefers_user_email(self, project_user, user):
        user.email = "ada@test.edu"
        login = AccountLifecycleService._fallback_login(project_user)
        assert login == "ada@test.edu"

    def test_falls_back_to_project_user_remote_login(self, project_user, user):
        user.email = None
        project_user.remote_site_login = "ada_pu"
        login = AccountLifecycleService._fallback_login(project_user)
        assert login == "ada_pu"

    def test_falls_back_to_user_remote_site_login(self, project_user, user):
        user.email = None
        project_user.remote_site_login = None
        user.remote_site_login = "ada_user"
        login = AccountLifecycleService._fallback_login(project_user)
        assert login == "ada_user"

    def test_falls_back_to_person_id(self, project_user, user):
        user.email = None
        project_user.remote_site_login = None
        user.remote_site_login = None
        user.person_id = "person-ada-001"
        login = AccountLifecycleService._fallback_login(project_user)
        assert login == "person-ada-001"

    def test_returns_none_when_no_login_info(self, project_user, user):
        user.email = None
        project_user.remote_site_login = None
        user.remote_site_login = None
        user.person_id = None
        login = AccountLifecycleService._fallback_login(project_user)
        assert login is None


# ===========================================================================
# _find_source_packet_rec_id
# ===========================================================================

class TestFindSourcePacketRecId:
    def test_returns_direct_source_packet_rec_id(self, db, svc, project_user):
        project_user.source_packet_rec_id = 7001
        result = svc._find_source_packet_rec_id(db, project_user)
        assert result == 7001

    def test_lookup_by_trans_rec_id(
        self, db, svc, project_user, source_packet, new_user_packet
    ):
        project_user.source_packet_rec_id = None
        project_user.source_trans_rec_id = source_packet.trans_rec_id
        result = svc._find_source_packet_rec_id(db, project_user)
        assert result == source_packet.packet_rec_id

    def test_lookup_by_project_id_and_person_id(
        self, db, svc, project_user, source_packet, new_user_packet, project
    ):
        project_user.source_packet_rec_id = None
        project_user.source_trans_rec_id = None
        project.site_project_id = "PROJ-001"
        result = svc._find_source_packet_rec_id(db, project_user)
        assert result == source_packet.packet_rec_id

    def test_returns_none_when_nothing_matches(self, db, svc, project_user):
        project_user.source_packet_rec_id = None
        project_user.source_trans_rec_id = None
        project_user.project.site_project_id = None
        result = svc._find_source_packet_rec_id(db, project_user)
        assert result is None


# ===========================================================================
# _send_account_confirmation_packet
# ===========================================================================

class TestSendAccountConfirmationPacket:
    def test_skips_if_already_confirmed(self, db, svc, project_user, mock_amie_client):
        project_user.aime_confirmation_sent_at = datetime.now(UTC)
        result = svc._send_account_confirmation_packet(
            db, project_user=project_user, amie_client=mock_amie_client
        )
        assert result is True
        mock_amie_client.get_packet.assert_not_called()

    def test_returns_false_when_no_source_packet(self, db, svc, project_user, mock_amie_client):
        project_user.source_packet_rec_id = None
        project_user.source_trans_rec_id = None
        project_user.project.site_project_id = None
        result = svc._send_account_confirmation_packet(
            db, project_user=project_user, amie_client=mock_amie_client
        )
        assert result is False

    def test_returns_false_when_missing_project_id(
        self, db, svc, project_user, source_packet, mock_amie_client
    ):
        project_user.source_packet_rec_id = source_packet.packet_rec_id
        project_user.project.site_project_id = None  # missing
        result = svc._send_account_confirmation_packet(
            db, project_user=project_user, amie_client=mock_amie_client
        )
        assert result is False

    def test_successful_confirmation(
        self, db, svc, project_user, source_packet, project, user, mock_amie_client
    ):
        project_user.source_packet_rec_id = source_packet.packet_rec_id
        project.site_project_id = "PROJ-001"
        project_user.resource = "supercomputer.test.edu"
        user.email = "ada@test.edu"

        # Mock amie_client.get_packet to return a packet with reply_packet()
        fake_source = MagicMock()
        nac_packet = MagicMock()
        fake_source.reply_packet.return_value = nac_packet
        mock_amie_client.get_packet.return_value = fake_source

        send_result = MagicMock()
        send_result.as_dict.return_value = {"header": {"packet_rec_id": 9999}}
        mock_amie_client.send_packet.return_value = send_result

        # Mock the outbound ack refresh so it doesn't fail on the fake packet
        mock_amie_client.get_packet.side_effect = [
            fake_source,         # first call: get source packet
            MagicMock(           # second call: get outbound packet for ack
                **{"get.return_value": {},
                   "header": MagicMock(transaction_state="complete")}
            ),
        ]

        result = svc._send_account_confirmation_packet(
            db, project_user=project_user, amie_client=mock_amie_client
        )
        assert result is True
        assert project_user.aime_confirmation_sent_at is not None

    def test_returns_false_on_amie_exception(
        self, db, svc, project_user, source_packet, project, user, mock_amie_client
    ):
        project_user.source_packet_rec_id = source_packet.packet_rec_id
        project.site_project_id = "PROJ-001"
        project_user.resource = "supercomputer.test.edu"
        user.email = "ada@test.edu"

        mock_amie_client.get_packet.side_effect = RuntimeError("AMIE is down")

        result = svc._send_account_confirmation_packet(
            db, project_user=project_user, amie_client=mock_amie_client
        )
        assert result is False


# ===========================================================================
# reconcile_pending_confirmations
# ===========================================================================

class TestReconcilePendingConfirmations:
    def test_skips_when_confirmation_disabled(self, db, svc, project_user):
        project_user.account_state = ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE
        db.flush()

        with patch("app.services.account_lifecycle.settings") as mock_settings:
            mock_settings.amie_account_confirmation_enabled = False
            mock_settings.amie_api_key = "key"
            mock_settings.amie_url = "https://example.com"
            mock_settings.amie_site_name = "NRP"
            mock_settings.amie_site_names = ""
            result = svc.reconcile_pending_confirmations(db)

        assert result["checked"] >= 1
        assert result["confirmations_sent"] == 0

    def test_returns_counts_dict(self, db, svc):
        result = svc.reconcile_pending_confirmations(db)
        assert "checked" in result
        assert "confirmations_sent" in result
        assert "failures" in result

    def test_handles_per_user_exception_gracefully(self, db, svc, project_user):
        """One bad ProjectUser must not abort reconciliation for others."""
        project_user.account_state = ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE
        db.flush()

        with patch.object(svc, "_send_account_confirmation_packet", side_effect=RuntimeError("boom")):
            with patch("app.services.account_lifecycle.settings") as mock_settings:
                mock_settings.amie_account_confirmation_enabled = True
                mock_settings.amie_api_key = "key"
                mock_settings.amie_url = "https://example.com"
                mock_settings.amie_site_name = "NRP"
                mock_settings.amie_site_names = ""
                result = svc.reconcile_pending_confirmations(db)

        assert result["failures"] >= 1
        # Should not have propagated the exception
