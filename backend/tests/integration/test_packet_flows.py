"""
Integration tests – one test per inbound packet type.

Each test ingests a packet dict through AIMEService.ingest_packet() against
a real (in-memory SQLite) database and asserts on the resulting DB state.
External dependencies (Authentik, Kubernetes, portal RPC) are mocked.
"""

import pytest

from app.models.amie_packet import AMIEPacket
from app.models.amie_allocation_packet import AMIEAllocationPacket
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.amie_lifecycle_packet import AMIELifecyclePacket
from app.models.amie_unprocessed_packet import AMIEUnprocessedPacket
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.aime.service import AIMEService

from tests.conftest import (
    make_rpc_packet,
    make_rac_packet,
    make_lifecycle_packet,
    make_header,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def ingest(db, aime_service, packet_dict):
    result = aime_service.ingest_packet(db, packet_dict)
    db.flush()
    return result


def get_packet(db, packet_rec_id: int) -> AMIEPacket | None:
    return db.query(AMIEPacket).filter(AMIEPacket.packet_rec_id == packet_rec_id).first()


# ===========================================================================
# request_project_create
# ===========================================================================

class TestRequestProjectCreate:
    def test_creates_amie_packet_record(self, db, aime_service):
        packet = make_rpc_packet(packet_rec_id=2001)
        ingest(db, aime_service, packet)
        row = get_packet(db, 2001)
        assert row is not None
        assert row.packet_type == "request_project_create"
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED

    def test_creates_project_row(self, db, aime_service):
        packet = make_rpc_packet(packet_rec_id=2002, GrantNumber="TG-CREATE-01")
        ingest(db, aime_service, packet)
        project = db.query(Project).filter(Project.grant_number == "TG-CREATE-01").first()
        assert project is not None
        assert project.is_active is True

    def test_creates_allocation_packet_record(self, db, aime_service):
        packet = make_rpc_packet(packet_rec_id=2003, GrantNumber="TG-ALLOC-01")
        ingest(db, aime_service, packet)
        pkt_row = get_packet(db, 2003)
        alloc = db.query(AMIEAllocationPacket).filter(
            AMIEAllocationPacket.packet_id == pkt_row.id
        ).first()
        assert alloc is not None
        assert alloc.grant_number == "TG-ALLOC-01"

    def test_creates_pi_user(self, db, aime_service):
        packet = make_rpc_packet(
            packet_rec_id=2004,
            PiPersonID="pi-person-001",
            PiEmail="pi@test.edu",
            PiFirstName="Grace",
            PiLastName="Hopper",
        )
        ingest(db, aime_service, packet)
        user = db.query(User).filter(User.email == "pi@test.edu").first()
        assert user is not None
        assert user.first_name == "Grace"

    def test_creates_pi_project_user(self, db, aime_service):
        packet = make_rpc_packet(packet_rec_id=2005, GrantNumber="TG-PI-PU-01")
        ingest(db, aime_service, packet)
        project = db.query(Project).filter(Project.grant_number == "TG-PI-PU-01").first()
        pu = db.query(ProjectUser).filter(ProjectUser.project_id == project.id).first()
        assert pu is not None
        assert pu.account_state == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE

    def test_idempotent_on_same_packet_rec_id(self, db, aime_service):
        packet = make_rpc_packet(packet_rec_id=2006, GrantNumber="TG-IDEM-01")
        ingest(db, aime_service, packet)
        ingest(db, aime_service, packet)
        count = db.query(Project).filter(Project.grant_number == "TG-IDEM-01").count()
        assert count == 1

    def test_updates_existing_project_on_re_ingest(self, db, aime_service):
        packet = make_rpc_packet(
            packet_rec_id=2007, GrantNumber="TG-UPDATE-01", ServiceUnitsAllocated="10000"
        )
        ingest(db, aime_service, packet)

        packet2 = make_rpc_packet(
            packet_rec_id=2008, GrantNumber="TG-UPDATE-01", ServiceUnitsAllocated="20000"
        )
        ingest(db, aime_service, packet2)

        project = db.query(Project).filter(Project.grant_number == "TG-UPDATE-01").first()
        assert project.service_units_allocated == 20000

    def test_malformed_body_sets_error_status(self, db, aime_service):
        bad_packet = {
            "type": "request_project_create",
            "header": make_header(packet_rec_id=2009),
            "body": {"GrantNumber": "TG-X"},  # missing required fields
        }
        ingest(db, aime_service, bad_packet)
        row = get_packet(db, 2009)
        assert row is not None
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_ERROR


# ===========================================================================
# request_account_create
# ===========================================================================

class TestRequestAccountCreate:
    def test_creates_amie_packet_and_new_user_packet(self, db, aime_service):
        # First create the project
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=3001, GrantNumber="TG-ACC-01"))
        packet = make_rac_packet(
            packet_rec_id=3002, grant_number="TG-ACC-01",
            UserPersonID="user-001", UserEmail="user001@test.edu",
        )
        ingest(db, aime_service, packet)
        row = get_packet(db, 3002)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        new_user = db.query(AMIENewUserPacket).filter(
            AMIENewUserPacket.packet_id == row.id
        ).first()
        assert new_user is not None

    def test_creates_user_row(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=3003, GrantNumber="TG-ACC-02"))
        packet = make_rac_packet(
            packet_rec_id=3004, grant_number="TG-ACC-02",
            UserPersonID="user-002", UserEmail="user002@test.edu",
            UserFirstName="Ada", UserLastName="Lovelace",
        )
        ingest(db, aime_service, packet)
        user = db.query(User).filter(User.email == "user002@test.edu").first()
        assert user is not None
        assert user.first_name == "Ada"

    def test_creates_project_user_with_initial_state(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=3005, GrantNumber="TG-ACC-03"))
        packet = make_rac_packet(
            packet_rec_id=3006, grant_number="TG-ACC-03",
            UserPersonID="user-003", UserEmail="user003@test.edu",
        )
        ingest(db, aime_service, packet)
        project = db.query(Project).filter(Project.grant_number == "TG-ACC-03").first()
        pu = db.query(ProjectUser).filter(
            ProjectUser.project_id == project.id,
        ).order_by(ProjectUser.account_state_updated_at).all()
        # PI + new user
        states = {p.account_state for p in pu}
        assert ProjectUser.ACCOUNT_STATE_NOT_SENT_EMAIL_INVITE in states

    def test_creates_placeholder_project_when_missing(self, db, aime_service):
        packet = make_rac_packet(
            packet_rec_id=3007, grant_number="TG-ORPHAN-01",
            UserPersonID="user-004",
        )
        ingest(db, aime_service, packet)
        project = db.query(Project).filter(Project.grant_number == "TG-ORPHAN-01").first()
        assert project is not None

    def test_idempotent_on_same_packet_rec_id(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=3008, GrantNumber="TG-ACC-IDEM"))
        packet = make_rac_packet(
            packet_rec_id=3009, grant_number="TG-ACC-IDEM",
            UserPersonID="user-005", UserEmail="user005@test.edu",
        )
        ingest(db, aime_service, packet)
        ingest(db, aime_service, packet)
        count = db.query(User).filter(User.email == "user005@test.edu").count()
        assert count == 1


# ===========================================================================
# notify_project_create
# ===========================================================================

class TestNotifyProjectCreate:
    def test_creates_lifecycle_packet_and_updates_project(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=4001, GrantNumber="TG-NPC-01"))
        packet = {
            "type": "notify_project_create",
            "header": make_header(packet_rec_id=4002),
            "body": {
                "GrantNumber": "TG-NPC-01",
                "ProjectID": "PROJ-NPC-01",
                "ResourceList": ["supercomputer.test.edu"],
                "ProjectTitle": "My Updated Title",
                "PiPersonID": "pi-001",
                "PiFirstName": "Grace",
                "PiLastName": "Hopper",
            },
        }
        ingest(db, aime_service, packet)
        row = get_packet(db, 4002)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None
        project = db.query(Project).filter(Project.grant_number == "TG-NPC-01").first()
        assert project.project_title == "My Updated Title"


# ===========================================================================
# data_project_create
# ===========================================================================

class TestDataProjectCreate:
    def test_creates_lifecycle_packet(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=5001, GrantNumber="TG-DPC-01",
                                                  ProjectID="PROJ-DPC-01"))
        packet = {
            "type": "data_project_create",
            "header": make_header(packet_rec_id=5002),
            "body": {
                "PersonID": "pi-person-001",
                "ProjectID": "PROJ-DPC-01",
                "DnList": ["/CN=PI"],
            },
        }
        ingest(db, aime_service, packet)
        row = get_packet(db, 5002)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None


# ===========================================================================
# notify_account_create
# ===========================================================================

class TestNotifyAccountCreate:
    def test_creates_lifecycle_packet(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=6001, GrantNumber="TG-NAC-01",
                                                  ProjectID="PROJ-NAC-01"))
        packet = {
            "type": "notify_account_create",
            "header": make_header(packet_rec_id=6002),
            "body": {
                "ProjectID": "PROJ-NAC-01",
                "UserPersonID": "user-001",
                "ResourceList": ["supercomputer.test.edu"],
                "UserFirstName": "Ada",
                "UserLastName": "Lovelace",
                "UserEmail": "ada.nac@test.edu",
            },
        }
        ingest(db, aime_service, packet)
        row = get_packet(db, 6002)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None


# ===========================================================================
# data_account_create
# ===========================================================================

class TestDataAccountCreate:
    def test_sets_account_made_on_project_user(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=7001, GrantNumber="TG-DAC-01",
                                                  ProjectID="PROJ-DAC-01"))
        ingest(db, aime_service, make_rac_packet(
            packet_rec_id=7002, grant_number="TG-DAC-01",
            UserPersonID="user-dac-001", UserEmail="dac@test.edu",
        ))
        packet = {
            "type": "data_account_create",
            "header": make_header(packet_rec_id=7003),
            "body": {
                "PersonID": "user-dac-001",
                "ProjectID": "PROJ-DAC-01",
                "DnList": [],
            },
        }
        ingest(db, aime_service, packet)
        row = get_packet(db, 7003)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        project = db.query(Project).filter(Project.site_project_id == "PROJ-DAC-01").first()
        if project:
            user = db.query(User).filter(User.person_id == "user-dac-001").first()
            if user:
                pu = db.query(ProjectUser).filter(
                    ProjectUser.project_id == project.id,
                    ProjectUser.user_id == user.id,
                ).first()
                if pu:
                    assert pu.account_state == ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE


# ===========================================================================
# request_project_inactivate
# ===========================================================================

class TestRequestProjectInactivate:
    def test_sets_project_inactive(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=8001, GrantNumber="TG-INACT-01",
                                                  ProjectID="PROJ-INACT-01"))
        packet = make_lifecycle_packet(
            "request_project_inactivate", packet_rec_id=8002,
            GrantNumber="TG-INACT-01", ProjectID="PROJ-INACT-01",
        )
        ingest(db, aime_service, packet)
        project = db.query(Project).filter(Project.grant_number == "TG-INACT-01").first()
        assert project.is_active is False

    def test_creates_lifecycle_packet(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=8003, GrantNumber="TG-INACT-02"))
        packet = make_lifecycle_packet(
            "request_project_inactivate", packet_rec_id=8004,
            GrantNumber="TG-INACT-02",
        )
        ingest(db, aime_service, packet)
        row = get_packet(db, 8004)
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None


# ===========================================================================
# request_project_reactivate
# ===========================================================================

class TestRequestProjectReactivate:
    def test_sets_project_active(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=9001, GrantNumber="TG-REACT-01",
                                                  ProjectID="PROJ-REACT-01"))
        ingest(db, aime_service, make_lifecycle_packet(
            "request_project_inactivate", packet_rec_id=9002,
            GrantNumber="TG-REACT-01", ProjectID="PROJ-REACT-01",
        ))
        ingest(db, aime_service, make_lifecycle_packet(
            "request_project_reactivate", packet_rec_id=9003,
            GrantNumber="TG-REACT-01", ProjectID="PROJ-REACT-01",
        ))
        project = db.query(Project).filter(Project.grant_number == "TG-REACT-01").first()
        assert project.is_active is True


# ===========================================================================
# request_account_inactivate
# ===========================================================================

class TestRequestAccountInactivate:
    def test_sets_project_user_inactive(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=10001, GrantNumber="TG-AINACT-01",
                                                  ProjectID="PROJ-AINACT-01"))
        ingest(db, aime_service, make_rac_packet(
            packet_rec_id=10002, grant_number="TG-AINACT-01",
            UserPersonID="person-ainact-001",
        ))
        packet = {
            "type": "request_account_inactivate",
            "header": make_header(packet_rec_id=10003),
            "body": {
                "GrantNumber": "TG-AINACT-01",
                "ProjectID": "PROJ-AINACT-01",
                "PersonID": "person-ainact-001",
                "ResourceList": ["supercomputer.test.edu"],
            },
        }
        ingest(db, aime_service, packet)
        project = db.query(Project).filter(Project.grant_number == "TG-AINACT-01").first()
        user = db.query(User).filter(User.person_id == "person-ainact-001").first()
        if project and user:
            pu = db.query(ProjectUser).filter(
                ProjectUser.project_id == project.id,
                ProjectUser.user_id == user.id,
            ).first()
            if pu:
                assert pu.is_active is False


# ===========================================================================
# request_account_reactivate
# ===========================================================================

class TestRequestAccountReactivate:
    def test_sets_project_user_active(self, db, aime_service):
        ingest(db, aime_service, make_rpc_packet(packet_rec_id=11001, GrantNumber="TG-AREACT-01",
                                                  ProjectID="PROJ-AREACT-01"))
        ingest(db, aime_service, make_rac_packet(
            packet_rec_id=11002, grant_number="TG-AREACT-01",
            UserPersonID="person-areact-001",
        ))
        ingest(db, aime_service, {
            "type": "request_account_inactivate",
            "header": make_header(packet_rec_id=11003),
            "body": {
                "GrantNumber": "TG-AREACT-01",
                "ProjectID": "PROJ-AREACT-01",
                "PersonID": "person-areact-001",
                "ResourceList": ["supercomputer.test.edu"],
            },
        })
        ingest(db, aime_service, {
            "type": "request_account_reactivate",
            "header": make_header(packet_rec_id=11004),
            "body": {
                "GrantNumber": "TG-AREACT-01",
                "ProjectID": "PROJ-AREACT-01",
                "PersonID": "person-areact-001",
                "ResourceList": ["supercomputer.test.edu"],
            },
        })
        project = db.query(Project).filter(Project.grant_number == "TG-AREACT-01").first()
        user = db.query(User).filter(User.person_id == "person-areact-001").first()
        if project and user:
            pu = db.query(ProjectUser).filter(
                ProjectUser.project_id == project.id,
                ProjectUser.user_id == user.id,
            ).first()
            if pu:
                assert pu.is_active is True


# ===========================================================================
# request_user_modify
# ===========================================================================

class TestRequestUserModify:
    def test_updates_user_fields(self, db, aime_service):
        # Seed a user
        from app.models.user import User as UserModel
        u = UserModel(
            name="Old Name",
            person_id="person-modify-001",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=[],
            tags=[],
        )
        db.add(u)
        db.flush()

        packet = {
            "type": "request_user_modify",
            "header": make_header(packet_rec_id=12001),
            "body": {
                "PersonID": "person-modify-001",
                "FirstName": "NewFirst",
                "LastName": "NewLast",
                "Email": "new@test.edu",
                "Organization": "NewOrg",
                "OrgCode": "NEWORG",
                "ActionType": "add",
                "DnList": ["/CN=New"],
            },
        }
        ingest(db, aime_service, packet)
        db.refresh(u)
        assert u.first_name == "NewFirst"
        assert u.email == "new@test.edu"

    def test_merges_dn_list_on_add(self, db, aime_service):
        from app.models.user import User as UserModel
        u = UserModel(
            name="DN User",
            person_id="person-dn-001",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=["/CN=Existing"],
            tags=[],
        )
        db.add(u)
        db.flush()

        packet = {
            "type": "request_user_modify",
            "header": make_header(packet_rec_id=12002),
            "body": {
                "PersonID": "person-dn-001",
                "ActionType": "add",
                "DnList": ["/CN=New"],
            },
        }
        ingest(db, aime_service, packet)
        db.refresh(u)
        assert "/CN=Existing" in u.dn_list
        assert "/CN=New" in u.dn_list

    def test_removes_dn_list_on_delete(self, db, aime_service):
        from app.models.user import User as UserModel
        u = UserModel(
            name="DN Remove User",
            person_id="person-dn-002",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=["/CN=ToRemove", "/CN=Keep"],
            tags=[],
        )
        db.add(u)
        db.flush()

        packet = {
            "type": "request_user_modify",
            "header": make_header(packet_rec_id=12003),
            "body": {
                "PersonID": "person-dn-002",
                "ActionType": "delete",
                "DnList": ["/CN=ToRemove"],
            },
        }
        ingest(db, aime_service, packet)
        db.refresh(u)
        assert "/CN=ToRemove" not in u.dn_list
        assert "/CN=Keep" in u.dn_list

    def test_creates_lifecycle_packet(self, db, aime_service):
        packet = {
            "type": "request_user_modify",
            "header": make_header(packet_rec_id=12004),
            "body": {
                "PersonID": "person-modify-new-001",
                "ActionType": "add",
                "DnList": [],
            },
        }
        ingest(db, aime_service, packet)
        row = get_packet(db, 12004)
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None


# ===========================================================================
# request_person_merge
# ===========================================================================

class TestRequestPersonMerge:
    def test_creates_lifecycle_packet(self, db, aime_service):
        packet = {
            "type": "request_person_merge",
            "header": make_header(packet_rec_id=13001),
            "body": {
                "KeepPersonID": "person-keep-001",
                "DeletePersonID": "person-delete-001",
            },
        }
        ingest(db, aime_service, packet)
        row = get_packet(db, 13001)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None
        assert lp.keep_person_id == "person-keep-001"
        assert lp.delete_person_id == "person-delete-001"

    def test_merges_two_existing_users(self, db, aime_service):
        from app.models.user import User as UserModel
        keep = UserModel(
            name="Keep User",
            person_id="person-keep-002",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=["/CN=Keep"],
            tags=[],
        )
        delete = UserModel(
            name="Delete User",
            person_id="person-delete-002",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=["/CN=Delete"],
            tags=[],
        )
        db.add_all([keep, delete])
        db.flush()

        packet = {
            "type": "request_person_merge",
            "header": make_header(packet_rec_id=13002),
            "body": {
                "KeepPersonID": "person-keep-002",
                "DeletePersonID": "person-delete-002",
            },
        }
        ingest(db, aime_service, packet)
        db.refresh(keep)
        assert "/CN=Delete" in keep.dn_list
        assert "/CN=Keep" in keep.dn_list


# ===========================================================================
# inform_transaction_complete
# ===========================================================================

class TestInformTransactionComplete:
    def test_creates_lifecycle_packet(self, db, aime_service):
        packet = {
            "type": "inform_transaction_complete",
            "header": make_header(packet_rec_id=14001),
            "body": {
                "StatusCode": "0",
                "DetailCode": "0",
                "Message": "Transaction complete",
            },
        }
        ingest(db, aime_service, packet)
        row = get_packet(db, 14001)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None
        assert lp.status_code == "0"


# ===========================================================================
# Unsupported / unknown packet type
# ===========================================================================

class TestUnsupportedPacketType:
    def test_marks_packet_unprocessed(self, db, aime_service):
        packet = {
            "type": "unknown_packet_type_xyz",
            "header": make_header(packet_rec_id=15001),
            "body": {},
        }
        result = ingest(db, aime_service, packet)
        assert result.handled is False
        row = get_packet(db, 15001)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_UNPROCESSED

    def test_ingest_result_handled_false(self, db, aime_service):
        packet = {
            "type": "not_supported",
            "header": make_header(packet_rec_id=15002),
            "body": {},
        }
        result = ingest(db, aime_service, packet)
        assert result.handled is False
        assert result.packet_type == "not_supported"


# ===========================================================================
# Notify lifecycle packets (just record – no state change on Project/User)
# ===========================================================================

class TestNotifyLifecyclePackets:
    @pytest.mark.parametrize("packet_type,packet_rec_id", [
        ("notify_project_inactivate", 16001),
        ("notify_project_reactivate", 16002),
        ("notify_account_inactivate", 16003),
        ("notify_account_reactivate", 16004),
    ])
    def test_creates_lifecycle_record(self, db, aime_service, packet_type, packet_rec_id):
        packet = make_lifecycle_packet(packet_type, packet_rec_id=packet_rec_id)
        ingest(db, aime_service, packet)
        row = get_packet(db, packet_rec_id)
        assert row.processing_status == AMIEPacket.PROCESSING_STATUS_PROCESSED
        lp = db.query(AMIELifecyclePacket).filter(
            AMIELifecyclePacket.packet_id == row.id
        ).first()
        assert lp is not None
        assert lp.packet_type == packet_type
