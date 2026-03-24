"""
Unit tests for app/services/aime/bindings.py.

Tests every Pydantic binding class: happy paths, optional fields,
type coercion, alias handling, single-resource validation, and the
bind_packet() dispatcher.
"""

import pytest
from pydantic import ValidationError

from app.services.aime.bindings import (
    AMIEPacketHeaderBinding,
    RequestProjectCreateBodyBinding,
    RequestAccountCreateBodyBinding,
    DataProjectCreateBodyBinding,
    DataAccountCreateBodyBinding,
    NotifyProjectCreateBodyBinding,
    NotifyAccountCreateBodyBinding,
    RequestProjectCreatePacketBinding,
    RequestAccountCreatePacketBinding,
    DataProjectCreatePacketBinding,
    DataAccountCreatePacketBinding,
    NotifyProjectCreatePacketBinding,
    NotifyAccountCreatePacketBinding,
    NotifyProjectInactivatePacketBinding,
    NotifyProjectReactivatePacketBinding,
    NotifyAccountInactivatePacketBinding,
    NotifyAccountReactivatePacketBinding,
    RequestProjectInactivatePacketBinding,
    RequestProjectReactivatePacketBinding,
    RequestAccountInactivatePacketBinding,
    RequestAccountReactivatePacketBinding,
    RequestUserModifyPacketBinding,
    RequestPersonMergePacketBinding,
    InformTransactionCompletePacketBinding,
    UnsupportedPacketType,
    bind_packet,
    coerce_packet_dict,
    PacketBindingError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_HEADER = {
    "packet_rec_id": 12345,
    "trans_rec_id": 6789,
    "packet_id": 111,
    "transaction_id": 222,
    "local_site_name": "NRP",
    "remote_site_name": "XSEDE",
    "originating_site_name": "XSEDE",
    "transaction_state": "in-progress",
    "packet_state": "",
}

VALID_RPC_BODY = {
    "AllocationType": "new",
    "EndDate": "2027-01-01",
    "GrantNumber": "TG-TEST001",
    "PfosNumber": "12345",
    "PiFirstName": "Jessica",
    "PiLastName": "Scienceperson",
    "PiOrganization": "PSC",
    "PiOrgCode": "12345",
    "StartDate": "2026-01-01",
    "ResourceList": ["supercomputer.test.edu"],
    "RecordID": "REC-001",
    "ServiceUnitsAllocated": "50000",
}

VALID_RAC_BODY = {
    "GrantNumber": "TG-TEST001",
    "ResourceList": ["supercomputer.test.edu"],
    "UserFirstName": "Ada",
    "UserLastName": "Lovelace",
    "UserOrganization": "PSC",
    "UserOrgCode": "99999",
}

VALID_NPC_BODY = {
    "GrantNumber": "TG-TEST001",
    "ProjectID": "PROJ-001",
    "ResourceList": ["supercomputer.test.edu"],
}

VALID_NAC_BODY = {
    "ProjectID": "PROJ-001",
    "UserPersonID": "person-001",
    "ResourceList": ["supercomputer.test.edu"],
}

VALID_DPC_BODY = {
    "PersonID": "person-pi-001",
    "ProjectID": "PROJ-001",
}

VALID_DAC_BODY = {
    "PersonID": "person-user-001",
    "ProjectID": "PROJ-001",
}

LIFECYCLE_BODY = {
    "GrantNumber": "TG-TEST001",
    "ProjectID": "PROJ-001",
    "PersonID": "person-001",
    "ResourceList": ["supercomputer.test.edu"],
}

INFORM_BODY = {
    "StatusCode": "0",
    "DetailCode": "0",
    "Message": "Success",
}

USER_MODIFY_BODY = {
    "PersonID": "person-001",
    "ActionType": "add",
}

PERSON_MERGE_BODY = {
    "KeepPersonID": "person-keep",
    "DeletePersonID": "person-delete",
}


def make_packet(packet_type: str, body: dict, header: dict | None = None) -> dict:
    return {
        "type": packet_type,
        "header": header or VALID_HEADER,
        "body": body,
    }


# ===========================================================================
# AMIEPacketHeaderBinding
# ===========================================================================

class TestAMIEPacketHeaderBinding:
    def test_valid_header(self):
        h = AMIEPacketHeaderBinding(**VALID_HEADER)
        assert h.packet_rec_id == 12345
        assert h.remote_site_name == "XSEDE"

    def test_all_optional_absent(self):
        h = AMIEPacketHeaderBinding(packet_rec_id=1)
        assert h.trans_rec_id is None
        assert h.transaction_state is None

    def test_extra_fields_ignored(self):
        h = AMIEPacketHeaderBinding(**VALID_HEADER, unexpected_field="ignored")
        assert not hasattr(h, "unexpected_field")

    def test_missing_packet_rec_id_raises(self):
        with pytest.raises(ValidationError):
            AMIEPacketHeaderBinding()


# ===========================================================================
# RequestProjectCreateBodyBinding
# ===========================================================================

class TestRequestProjectCreateBodyBinding:
    def test_valid_body(self):
        b = RequestProjectCreateBodyBinding(**VALID_RPC_BODY)
        assert b.GrantNumber == "TG-TEST001"
        assert b.PiFirstName == "Jessica"
        assert b.ServiceUnitsAllocated == "50000"

    def test_service_units_as_int(self):
        body = {**VALID_RPC_BODY, "ServiceUnitsAllocated": 50000}
        b = RequestProjectCreateBodyBinding(**body)
        assert b.ServiceUnitsAllocated == 50000

    def test_service_units_as_float(self):
        body = {**VALID_RPC_BODY, "ServiceUnitsAllocated": 50000.5}
        b = RequestProjectCreateBodyBinding(**body)
        assert b.ServiceUnitsAllocated == 50000.5

    def test_optional_fields_default(self):
        b = RequestProjectCreateBodyBinding(**VALID_RPC_BODY)
        assert b.Abstract is None
        assert b.PiDnList == []
        assert b.RoleList == []

    def test_pi_dn_list_populated(self):
        body = {**VALID_RPC_BODY, "PiDnList": ["/CN=Ada"]}
        b = RequestProjectCreateBodyBinding(**body)
        assert b.PiDnList == ["/CN=Ada"]

    def test_nsf_status_code_alias(self):
        """Both NsfStatusCode and PiNsfStatusCode should be accepted."""
        body_v1 = {**VALID_RPC_BODY, "NsfStatusCode": "US"}
        body_v2 = {**VALID_RPC_BODY, "PiNsfStatusCode": "US"}
        b1 = RequestProjectCreateBodyBinding(**body_v1)
        b2 = RequestProjectCreateBodyBinding(**body_v2)
        assert b1.NsfStatusCode == "US"
        assert b2.NsfStatusCode == "US"

    def test_single_resource_required(self):
        body = {**VALID_RPC_BODY, "ResourceList": ["r1", "r2"]}
        with pytest.raises(ValidationError, match="ResourceList must contain exactly one entry"):
            RequestProjectCreateBodyBinding(**body)

    def test_empty_resource_list_raises(self):
        body = {**VALID_RPC_BODY, "ResourceList": []}
        with pytest.raises(ValidationError):
            RequestProjectCreateBodyBinding(**body)

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            RequestProjectCreateBodyBinding(GrantNumber="TG-X")


# ===========================================================================
# RequestAccountCreateBodyBinding
# ===========================================================================

class TestRequestAccountCreateBodyBinding:
    def test_valid_body(self):
        b = RequestAccountCreateBodyBinding(**VALID_RAC_BODY)
        assert b.GrantNumber == "TG-TEST001"
        assert b.UserFirstName == "Ada"

    def test_optional_fields_default(self):
        b = RequestAccountCreateBodyBinding(**VALID_RAC_BODY)
        assert b.UserPersonID is None
        assert b.UserEmail is None
        assert b.UserDnList == []

    def test_nsf_alias(self):
        body = {**VALID_RAC_BODY, "UserNsfStatusCode": "US"}
        b = RequestAccountCreateBodyBinding(**body)
        assert b.NsfStatusCode == "US"

    def test_single_resource_required(self):
        body = {**VALID_RAC_BODY, "ResourceList": ["r1", "r2"]}
        with pytest.raises(ValidationError):
            RequestAccountCreateBodyBinding(**body)

    def test_missing_required_fields_raises(self):
        with pytest.raises(ValidationError):
            RequestAccountCreateBodyBinding(GrantNumber="TG-X")


# ===========================================================================
# DataProjectCreateBodyBinding / DataAccountCreateBodyBinding
# ===========================================================================

class TestDataBodyBindings:
    def test_data_project_create(self):
        b = DataProjectCreateBodyBinding(**VALID_DPC_BODY)
        assert b.PersonID == "person-pi-001"
        assert b.ProjectID == "PROJ-001"
        assert b.DnList == []

    def test_data_account_create(self):
        b = DataAccountCreateBodyBinding(**VALID_DAC_BODY)
        assert b.PersonID == "person-user-001"
        assert b.DnList == []

    def test_dn_list_populated(self):
        b = DataProjectCreateBodyBinding(**VALID_DPC_BODY, DnList=["/CN=Test"])
        assert b.DnList == ["/CN=Test"]


# ===========================================================================
# NotifyProjectCreateBodyBinding / NotifyAccountCreateBodyBinding
# ===========================================================================

class TestNotifyBodyBindings:
    def test_notify_project_create_minimal(self):
        b = NotifyProjectCreateBodyBinding(**VALID_NPC_BODY)
        assert b.GrantNumber == "TG-TEST001"
        assert b.ProjectID == "PROJ-001"

    def test_notify_project_create_single_resource(self):
        body = {**VALID_NPC_BODY, "ResourceList": ["r1", "r2"]}
        with pytest.raises(ValidationError):
            NotifyProjectCreateBodyBinding(**body)

    def test_notify_account_create_minimal(self):
        b = NotifyAccountCreateBodyBinding(**VALID_NAC_BODY)
        assert b.ProjectID == "PROJ-001"

    def test_notify_account_create_single_resource(self):
        body = {**VALID_NAC_BODY, "ResourceList": ["r1", "r2"]}
        with pytest.raises(ValidationError):
            NotifyAccountCreateBodyBinding(**body)

    def test_notify_account_nsf_alias(self):
        body = {**VALID_NAC_BODY, "UserNsfStatusCode": "US"}
        b = NotifyAccountCreateBodyBinding(**body)
        assert b.NsfStatusCode == "US"


# ===========================================================================
# bind_packet() dispatcher
# ===========================================================================

PACKET_TYPE_BINDING_MAP = [
    ("request_project_create", VALID_RPC_BODY, RequestProjectCreatePacketBinding),
    ("request_account_create", VALID_RAC_BODY, RequestAccountCreatePacketBinding),
    ("data_project_create", VALID_DPC_BODY, DataProjectCreatePacketBinding),
    ("data_account_create", VALID_DAC_BODY, DataAccountCreatePacketBinding),
    ("notify_project_create", VALID_NPC_BODY, NotifyProjectCreatePacketBinding),
    ("notify_account_create", VALID_NAC_BODY, NotifyAccountCreatePacketBinding),
    ("notify_project_inactivate", LIFECYCLE_BODY, NotifyProjectInactivatePacketBinding),
    ("notify_project_reactivate", LIFECYCLE_BODY, NotifyProjectReactivatePacketBinding),
    ("notify_account_inactivate", LIFECYCLE_BODY, NotifyAccountInactivatePacketBinding),
    ("notify_account_reactivate", LIFECYCLE_BODY, NotifyAccountReactivatePacketBinding),
    ("request_project_inactivate", LIFECYCLE_BODY, RequestProjectInactivatePacketBinding),
    ("request_project_reactivate", LIFECYCLE_BODY, RequestProjectReactivatePacketBinding),
    ("request_account_inactivate", LIFECYCLE_BODY, RequestAccountInactivatePacketBinding),
    ("request_account_reactivate", LIFECYCLE_BODY, RequestAccountReactivatePacketBinding),
    ("request_user_modify", USER_MODIFY_BODY, RequestUserModifyPacketBinding),
    ("request_person_merge", PERSON_MERGE_BODY, RequestPersonMergePacketBinding),
    # request_user_merge maps to RequestPersonMergePacketBinding
    ("request_user_merge", PERSON_MERGE_BODY, RequestPersonMergePacketBinding),
    ("inform_transaction_complete", INFORM_BODY, InformTransactionCompletePacketBinding),
]


class TestBindPacketDispatcher:
    @pytest.mark.parametrize(
        "packet_type, body, expected_cls",
        PACKET_TYPE_BINDING_MAP,
        ids=[row[0] for row in PACKET_TYPE_BINDING_MAP],
    )
    def test_dispatch(self, packet_type, body, expected_cls):
        packet = make_packet(packet_type, body)
        bound = bind_packet(packet)
        assert isinstance(bound, expected_cls)

    def test_unknown_type_raises_unsupported(self):
        packet = make_packet("not_a_real_type", {})
        with pytest.raises(UnsupportedPacketType):
            bind_packet(packet)

    def test_none_type_raises_unsupported(self):
        packet = {"type": None, "header": VALID_HEADER, "body": {}}
        with pytest.raises(UnsupportedPacketType):
            bind_packet(packet)

    def test_missing_type_key_raises(self):
        packet = {"header": VALID_HEADER, "body": VALID_RPC_BODY}
        with pytest.raises(UnsupportedPacketType):
            bind_packet(packet)

    def test_validation_error_on_bad_body(self):
        """bind_packet raises ValidationError for type-matched but invalid body."""
        packet = make_packet("request_project_create", {"GrantNumber": "X"})
        with pytest.raises(Exception):  # ValidationError or UnsupportedPacketType
            bind_packet(packet)


# ===========================================================================
# coerce_packet_dict()
# ===========================================================================

class TestCoercePacketDict:
    def test_dict_passthrough(self):
        d = {"type": "request_project_create"}
        assert coerce_packet_dict(d) is d

    def test_object_with_as_dict(self):
        class FakePkt:
            def as_dict(self):
                return {"type": "request_project_create"}

        result = coerce_packet_dict(FakePkt())
        assert result == {"type": "request_project_create"}

    def test_unsupported_type_raises(self):
        with pytest.raises(PacketBindingError):
            coerce_packet_dict(42)


# ===========================================================================
# Packet-level binding objects (header + body wired together)
# ===========================================================================

class TestPacketBindingObjects:
    def test_request_project_create_full(self):
        packet = make_packet("request_project_create", VALID_RPC_BODY)
        bound = bind_packet(packet)
        assert bound.type == "request_project_create"
        assert bound.header.packet_rec_id == VALID_HEADER["packet_rec_id"]
        assert bound.body.GrantNumber == "TG-TEST001"

    def test_request_account_create_full(self):
        packet = make_packet("request_account_create", VALID_RAC_BODY)
        bound = bind_packet(packet)
        assert bound.type == "request_account_create"
        assert bound.body.GrantNumber == "TG-TEST001"

    def test_inform_transaction_complete_full(self):
        packet = make_packet("inform_transaction_complete", INFORM_BODY)
        bound = bind_packet(packet)
        assert bound.type == "inform_transaction_complete"
        assert bound.body.StatusCode == "0"

    def test_request_person_merge_full(self):
        packet = make_packet("request_person_merge", PERSON_MERGE_BODY)
        bound = bind_packet(packet)
        assert bound.body.KeepPersonID == "person-keep"
        assert bound.body.DeletePersonID == "person-delete"

    def test_extra_body_fields_ignored(self):
        """Bindings with extra='allow' preserve extra fields; others ignore them."""
        body = {**VALID_RPC_BODY, "SomeUnknownField": "value"}
        packet = make_packet("request_project_create", body)
        bound = bind_packet(packet)
        assert bound.body.GrantNumber == "TG-TEST001"
