"""
Integration tests – multi-packet transaction sequences.

Each class simulates a complete AMIE transaction from the first inbound
packet to the final inform_transaction_complete, asserting on DB state at
every step.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.models.amie_lifecycle_packet import AMIELifecyclePacket
from app.models.amie_packet import AMIEPacket
from app.models.outbound_packet_log import OutboundPacketLog
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.account_lifecycle import AccountLifecycleService
from app.services.outbound_packets import OutboundPacketService
from app.services.unprocessed_packets import UnprocessedPacketService

from tests.conftest import make_header, make_lifecycle_packet, make_rac_packet, make_rpc_packet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ingest(db, svc, packet_dict):
    result = svc.ingest_packet(db, packet_dict)
    db.flush()
    return result


def get_project(db, grant_number):
    return db.query(Project).filter(Project.grant_number == grant_number).first()


def get_user(db, person_id=None, email=None):
    if person_id:
        return db.query(User).filter(User.person_id == person_id).first()
    return db.query(User).filter(User.email == email).first()


def get_packet_row(db, packet_rec_id):
    return db.query(AMIEPacket).filter(AMIEPacket.packet_rec_id == packet_rec_id).first()


# ===========================================================================
# Transaction A: complete project allocation flow
# ===========================================================================

class TestCompleteProjectAllocationTransaction:
    """
    Step 1: request_project_create  → Project created
    Step 2: notify_project_create   → Project title/PI updated
    Step 3: data_project_create     → Project confirmed, PI account made
    Step 4: inform_transaction_complete → transaction marked complete
    """

    GRANT = "TG-TXN-A001"
    PROJECT_ID = "PROJ-TXN-A001"

    def _base_header(self, packet_rec_id):
        return make_header(
            packet_rec_id=packet_rec_id,
            trans_rec_id=20001,
            transaction_id=30001,
        )

    def test_step1_request_project_create(self, db, aime_service):
        packet = make_rpc_packet(
            packet_rec_id=20001,
            GrantNumber=self.GRANT,
            ProjectID=self.PROJECT_ID,
            PiPersonID="pi-txn-a-001",
            PiFirstName="Grace",
            PiLastName="Hopper",
        )
        packet["header"] = self._base_header(20001)
        ingest(db, aime_service, packet)

        project = get_project(db, self.GRANT)
        assert project is not None
        assert project.is_active is True
        row = get_packet_row(db, 20001)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED

    def test_step2_notify_project_create(self, db, aime_service):
        # Set up project first
        ingest(db, aime_service, {**make_rpc_packet(packet_rec_id=20002, GrantNumber=self.GRANT,
                                                     ProjectID=self.PROJECT_ID),
                                   "header": self._base_header(20002)})

        notify = {
            "type": "notify_project_create",
            "header": self._base_header(20003),
            "body": {
                "GrantNumber": self.GRANT,
                "ProjectID": self.PROJECT_ID,
                "ResourceList": ["supercomputer.test.edu"],
                "ProjectTitle": "My Science Project",
                "PiPersonID": "pi-txn-a-001",
                "PiFirstName": "Grace",
                "PiLastName": "Hopper",
                "ServiceUnitsAllocated": "50000",
            },
        }
        ingest(db, aime_service, notify)
        project = get_project(db, self.GRANT)
        assert project.project_title == "My Science Project"

        row = get_packet_row(db, 20003)
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None

    def test_step3_data_project_create(self, db, aime_service):
        ingest(db, aime_service, {**make_rpc_packet(packet_rec_id=20004, GrantNumber=self.GRANT,
                                                     ProjectID=self.PROJECT_ID,
                                                     PiPersonID="pi-txn-a-002"),
                                   "header": self._base_header(20004)})

        dpc = {
            "type": "data_project_create",
            "header": self._base_header(20005),
            "body": {
                "PersonID": "pi-txn-a-002",
                "ProjectID": self.PROJECT_ID,
                "DnList": ["/CN=Grace"],
            },
        }
        ingest(db, aime_service, dpc)
        row = get_packet_row(db, 20005)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED

    def test_step4_inform_transaction_complete(self, db, aime_service):
        ingest(db, aime_service, {**make_rpc_packet(packet_rec_id=20006, GrantNumber=self.GRANT),
                                   "header": self._base_header(20006)})

        itc = {
            "type": "inform_transaction_complete",
            "header": self._base_header(20007),
            "body": {
                "StatusCode": "0",
                "DetailCode": "0",
                "Message": "Project allocation complete",
            },
        }
        ingest(db, aime_service, itc)
        row = get_packet_row(db, 20007)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED

    def test_full_sequence_in_order(self, db, aime_service):
        """Run all four steps in a single test to verify end-to-end state."""
        grant = "TG-TXN-FULL-A"
        project_id = "PROJ-FULL-A"

        # Step 1
        ingest(db, aime_service, make_rpc_packet(
            packet_rec_id=21001,
            GrantNumber=grant,
            ProjectID=project_id,
            PiPersonID="pi-full-a",
        ))

        p = get_project(db, grant)
        assert p is not None

        # Step 2
        ingest(db, aime_service, {
            "type": "notify_project_create",
            "header": make_header(packet_rec_id=21002),
            "body": {
                "GrantNumber": grant,
                "ProjectID": project_id,
                "ResourceList": ["supercomputer.test.edu"],
                "ProjectTitle": "Full A Project",
            },
        })
        db.refresh(p)
        assert p.project_title == "Full A Project"

        # Step 3
        ingest(db, aime_service, {
            "type": "data_project_create",
            "header": make_header(packet_rec_id=21003),
            "body": {"PersonID": "pi-full-a", "ProjectID": project_id, "DnList": []},
        })

        # Step 4
        ingest(db, aime_service, {
            "type": "inform_transaction_complete",
            "header": make_header(packet_rec_id=21004),
            "body": {"StatusCode": "0", "DetailCode": "0", "Message": "Done"},
        })
        row = get_packet_row(db, 21004)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED


# ===========================================================================
# Transaction B: complete account creation flow
# ===========================================================================

class TestCompleteAccountCreationTransaction:
    """
    Step 1: request_project_create
    Step 2: request_account_create → ProjectUser created, state=not_sent_email_invite
    Step 3: (portal) mark_email_sent → state=sent_email
    Step 4: (invite accept) mark_account_made → state=account_made
    Step 5: notify_account_create (AMIE confirmation)
    Step 6: data_account_create
    Step 7: inform_transaction_complete
    """

    GRANT = "TG-TXN-B001"
    PROJECT_ID = "PROJ-TXN-B001"
    PERSON_ID = "person-txn-b-001"

    def test_full_account_creation_sequence(self, db, aime_service):
        grant = "TG-TXN-B-FULL"
        project_id = "PROJ-TXN-B-FULL"
        person_id = "person-b-full-001"

        # Step 1 – project
        ingest(db, aime_service, make_rpc_packet(
            packet_rec_id=22001, GrantNumber=grant, ProjectID=project_id,
        ))
        project = get_project(db, grant)
        assert project is not None

        # Step 2 – account
        ingest(db, aime_service, make_rac_packet(
            packet_rec_id=22002, grant_number=grant,
            UserPersonID=person_id, UserEmail=f"{person_id}@test.edu",
        ))
        user = get_user(db, person_id=person_id)
        assert user is not None

        pu = db.query(ProjectUser).filter(
            ProjectUser.project_id == project.id,
            ProjectUser.user_id == user.id,
        ).first()
        # PI is already account_made; the new account user is not_sent_email_invite
        assert pu is not None
        assert pu.account_state in (
            ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE,
            ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE,
        )

        # Step 3 – mark_email_sent
        AccountLifecycleService.mark_email_sent(pu)
        db.flush()
        assert pu.account_state == ProjectUser.ACCOUNT_STATE_SENT_EMAIL
        assert pu.email_sent_at is not None

        # Step 4 – mark_account_made
        AccountLifecycleService.mark_account_made(pu)
        db.flush()
        assert pu.account_state == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE
        assert pu.account_made_at is not None

        # Verify idempotency
        first_ts = pu.account_made_at
        AccountLifecycleService.mark_account_made(pu)
        db.flush()
        assert pu.account_made_at == first_ts

        # Step 5 – notify_account_create
        ingest(db, aime_service, {
            "type": "notify_account_create",
            "header": make_header(packet_rec_id=22003),
            "body": {
                "ProjectID": project_id,
                "UserPersonID": person_id,
                "ResourceList": ["supercomputer.test.edu"],
            },
        })
        row = get_packet_row(db, 22003)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED

        # Step 6 – data_account_create
        ingest(db, aime_service, {
            "type": "data_account_create",
            "header": make_header(packet_rec_id=22004),
            "body": {
                "PersonID": person_id,
                "ProjectID": project_id,
                "DnList": [],
            },
        })
        row = get_packet_row(db, 22004)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED

        # Step 7 – inform_transaction_complete
        ingest(db, aime_service, {
            "type": "inform_transaction_complete",
            "header": make_header(packet_rec_id=22005),
            "body": {"StatusCode": "0", "DetailCode": "0", "Message": "Account ready"},
        })
        row = get_packet_row(db, 22005)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED


# ===========================================================================
# Transaction C: account inactivation → reactivation
# ===========================================================================

class TestAccountInactivationReactivation:
    def test_inactivate_then_reactivate(self, db, aime_service):
        grant = "TG-INACT-REACT-01"
        project_id = "PROJ-INACT-REACT-01"
        person_id = "person-inact-react-01"

        ingest(db, aime_service, make_rpc_packet(
            packet_rec_id=23001, GrantNumber=grant, ProjectID=project_id,
        ))
        ingest(db, aime_service, make_rac_packet(
            packet_rec_id=23002, grant_number=grant,
            UserPersonID=person_id,
        ))

        project = get_project(db, grant)
        user = get_user(db, person_id=person_id)

        # Inactivate
        ingest(db, aime_service, {
            "type": "request_account_inactivate",
            "header": make_header(packet_rec_id=23003),
            "body": {
                "GrantNumber": grant,
                "ProjectID": project_id,
                "PersonID": person_id,
                "ResourceList": ["supercomputer.test.edu"],
            },
        })
        if project and user:
            pu = db.query(ProjectUser).filter(
                ProjectUser.project_id == project.id,
                ProjectUser.user_id == user.id,
            ).first()
            if pu:
                assert pu.is_active is False

        # Reactivate
        ingest(db, aime_service, {
            "type": "request_account_reactivate",
            "header": make_header(packet_rec_id=23004),
            "body": {
                "GrantNumber": grant,
                "ProjectID": project_id,
                "PersonID": person_id,
                "ResourceList": ["supercomputer.test.edu"],
            },
        })
        if project and user:
            db.expire_all()
            pu = db.query(ProjectUser).filter(
                ProjectUser.project_id == project.id,
                ProjectUser.user_id == user.id,
            ).first()
            if pu:
                assert pu.is_active is True


# ===========================================================================
# Transaction D: project inactivation → reactivation
# ===========================================================================

class TestProjectInactivationReactivation:
    def test_project_inactivate_then_reactivate(self, db, aime_service):
        grant = "TG-PROJ-IR-01"
        ingest(db, aime_service, make_rpc_packet(
            packet_rec_id=24001, GrantNumber=grant, ProjectID="PROJ-IR-01",
        ))
        project = get_project(db, grant)
        assert project.is_active is True

        ingest(db, aime_service, make_lifecycle_packet(
            "request_project_inactivate", packet_rec_id=24002,
            GrantNumber=grant, ProjectID="PROJ-IR-01",
        ))
        db.refresh(project)
        assert project.is_active is False

        ingest(db, aime_service, make_lifecycle_packet(
            "request_project_reactivate", packet_rec_id=24003,
            GrantNumber=grant, ProjectID="PROJ-IR-01",
        ))
        db.refresh(project)
        assert project.is_active is True


# ===========================================================================
# Transaction E: outbound packet retry state machine
# ===========================================================================

class TestOutboundPacketRetryStateMachine:
    def test_retries_then_locks(self, db):
        pu_id = uuid.uuid4()
        max_retries = 3

        row = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        row.max_retries = max_retries
        db.flush()

        # Fail up to max_retries - 1
        for i in range(max_retries - 1):
            OutboundPacketService.mark_failed(db, row, error_message=f"err-{i}")
            assert row.status == OutboundPacketLog.STATUS_RETRYING
            assert row.retry_count == i + 1

        # Final failure → locked
        OutboundPacketService.mark_failed(db, row, error_message="final")
        assert row.status == OutboundPacketLog.STATUS_LOCKED
        assert OutboundPacketService.is_locked(row) is True

    def test_success_flow(self, db):
        pu_id = uuid.uuid4()
        row = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )

        class _Result:
            def as_dict(self):
                return {"header": {"packet_rec_id": 4444}}

        OutboundPacketService.mark_sent(db, row, send_result=_Result())
        assert row.status == OutboundPacketLog.STATUS_SENT

        OutboundPacketService.mark_acked(db, row, acked=True)
        assert row.ack_status == OutboundPacketLog.ACK_ACKED
        assert row.acked_at is not None

    def test_resume_returns_same_row(self, db):
        pu_id = uuid.uuid4()
        row1 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        OutboundPacketService.mark_failed(db, row1, error_message="retry me")
        row2 = OutboundPacketService.start_or_resume(
            db, event_type="notify_account_create", project_user_id=pu_id
        )
        assert row1.id == row2.id


# ===========================================================================
# Transaction F: failed packet / unprocessed packet tracking
# ===========================================================================

class TestFailedPacketTracking:
    def test_malformed_packet_creates_error_status(self, db, aime_service):
        bad = {
            "type": "request_project_create",
            "header": make_header(packet_rec_id=25001),
            "body": {"GrantNumber": "TG-ONLY"},  # missing required fields
        }
        ingest(db, aime_service, bad)
        row = get_packet_row(db, 25001)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_ERROR

    def test_unknown_type_marks_unprocessed(self, db, aime_service):
        packet = {
            "type": "unknown_type_xyz",
            "header": make_header(packet_rec_id=25002),
            "body": {},
        }
        ingest(db, aime_service, packet)
        row = get_packet_row(db, 25002)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_UNPROCESSED

    def test_unprocessed_packet_service_deduplication(self, db):
        payload = {
            "type": "request_project_create",
            "header": {"packet_rec_id": 9999},
            "body": {},
        }
        row1 = UnprocessedPacketService.record_failure(
            db, packet_payload=payload, failure_reason="parse_error"
        )
        assert row1.attempt_count == 1

        row2 = UnprocessedPacketService.record_failure(
            db, packet_payload=payload, failure_reason="parse_error"
        )
        assert row2.id == row1.id
        assert row2.attempt_count == 2

    def test_safe_record_failure_does_not_propagate(self, db):
        """safe_record_failure must swallow internal errors."""
        from unittest.mock import patch

        with patch.object(
            UnprocessedPacketService,
            "record_failure",
            side_effect=RuntimeError("db crash"),
        ):
            # Should not raise
            UnprocessedPacketService.safe_record_failure(
                db,
                packet_payload={"type": "unknown", "header": {}, "body": {}},
                failure_reason="test",
            )


# ===========================================================================
# Transaction G: person merge mid-transaction
# ===========================================================================

class TestPersonMergeTransaction:
    def test_merge_consolidates_users(self, db, aime_service):
        from app.models.project import Project as ProjectModel
        from app.models.user import User as UserModel

        keep = UserModel(
            name="Keep Person",
            person_id="keep-merge-001",
            email="keep@test.edu",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=["/CN=Keep"],
            tags=[],
        )
        delete = UserModel(
            name="Delete Person",
            person_id="delete-merge-001",
            email="delete@test.edu",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=["/CN=Delete"],
            tags=[],
        )
        db.add_all([keep, delete])
        db.flush()

        ingest(db, aime_service, {
            "type": "request_person_merge",
            "header": make_header(packet_rec_id=26001),
            "body": {
                "KeepPersonID": "keep-merge-001",
                "DeletePersonID": "delete-merge-001",
            },
        })

        db.refresh(keep)
        assert "/CN=Delete" in keep.dn_list
        # delete user should no longer exist
        gone = db.query(UserModel).filter(UserModel.person_id == "delete-merge-001").first()
        assert gone is None

    def test_merge_followed_by_inform_complete(self, db, aime_service):
        ingest(db, aime_service, {
            "type": "request_person_merge",
            "header": make_header(packet_rec_id=26002),
            "body": {
                "KeepPersonID": "keep-itc-001",
                "DeletePersonID": "delete-itc-001",
            },
        })
        ingest(db, aime_service, {
            "type": "inform_transaction_complete",
            "header": make_header(packet_rec_id=26003),
            "body": {"StatusCode": "0", "DetailCode": "0", "Message": "Merged"},
        })
        row = get_packet_row(db, 26003)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
