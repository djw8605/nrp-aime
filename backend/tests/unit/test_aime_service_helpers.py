"""
Unit tests for internal helper methods in app/services/aime/service.py.

These are tested by instantiating AIMEService with mocked dependencies
and calling the static/instance helpers directly.
"""

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pytest

from app.models.project import Project
from app.models.user import User
from app.services.aime.service import AIMEService


# ---------------------------------------------------------------------------
# Fixture: lightweight AIMEService (mocks injected via conftest fixtures)
# ---------------------------------------------------------------------------

@pytest.fixture
def svc(mock_authentik, mock_kubernetes, mock_provisioning):
    return AIMEService(
        site_name="NRP",
        authentik_service=mock_authentik,
        kubernetes_service=mock_kubernetes,
        project_provisioning_service=mock_provisioning,
    )


# ===========================================================================
# _full_name
# ===========================================================================

class TestFullName:
    def test_all_parts(self):
        assert AIMEService._full_name("Ada", "B.", "Lovelace") == "Ada B. Lovelace"

    def test_no_middle(self):
        assert AIMEService._full_name("Ada", None, "Lovelace") == "Ada Lovelace"

    def test_only_first(self):
        assert AIMEService._full_name("Ada", None, None) == "Ada"

    def test_all_none(self):
        assert AIMEService._full_name(None, None, None) == ""

    def test_strips_whitespace(self):
        assert AIMEService._full_name("  Ada ", "  ", " Lovelace ") == "Ada Lovelace"

    def test_empty_string_parts_skipped(self):
        assert AIMEService._full_name("Ada", "", "Lovelace") == "Ada Lovelace"


# ===========================================================================
# _to_date
# ===========================================================================

class TestToDate:
    def test_date_passthrough(self):
        d = date(2026, 1, 1)
        assert AIMEService._to_date(d) == d

    def test_datetime_to_date(self):
        dt = datetime(2026, 6, 15, 12, 0, 0)
        assert AIMEService._to_date(dt) == date(2026, 6, 15)

    def test_none_returns_none(self):
        assert AIMEService._to_date(None) is None


# ===========================================================================
# _to_decimal
# ===========================================================================

class TestToDecimal:
    def test_string_integer(self):
        assert AIMEService._to_decimal("50000") == Decimal("50000")

    def test_string_float(self):
        assert AIMEService._to_decimal("50000.5") == Decimal("50000.5")

    def test_int_input(self):
        assert AIMEService._to_decimal(50000) == Decimal("50000")

    def test_float_input(self):
        result = AIMEService._to_decimal(1.5)
        assert result is not None
        assert abs(result - Decimal("1.5")) < Decimal("0.0001")

    def test_none_returns_none(self):
        assert AIMEService._to_decimal(None) is None

    def test_invalid_string_returns_none(self):
        assert AIMEService._to_decimal("not-a-number") is None

    def test_empty_string_returns_none(self):
        assert AIMEService._to_decimal("") is None


# ===========================================================================
# _merge_dn_list
# ===========================================================================

class TestMergeDnList:
    def test_merges_two_lists(self):
        result = AIMEService._merge_dn_list(["/CN=A"], ["/CN=B"])
        assert result == ["/CN=A", "/CN=B"]

    def test_deduplicates(self):
        result = AIMEService._merge_dn_list(["/CN=A"], ["/CN=A", "/CN=B"])
        assert result == ["/CN=A", "/CN=B"]

    def test_preserves_order(self):
        result = AIMEService._merge_dn_list(["/CN=A", "/CN=B"], ["/CN=C"])
        assert result == ["/CN=A", "/CN=B", "/CN=C"]

    def test_handles_none_existing(self):
        result = AIMEService._merge_dn_list(None, ["/CN=A"])
        assert result == ["/CN=A"]

    def test_handles_none_incoming(self):
        result = AIMEService._merge_dn_list(["/CN=A"], None)
        assert result == ["/CN=A"]

    def test_both_none_returns_empty(self):
        result = AIMEService._merge_dn_list(None, None)
        assert result == []

    def test_strips_whitespace_before_dedup(self):
        result = AIMEService._merge_dn_list([" /CN=A "], ["/CN=A"])
        # Both are the same after stripping; result should deduplicate
        assert len(result) == 1


# ===========================================================================
# _remove_dn_list
# ===========================================================================

class TestRemoveDnList:
    def test_removes_matching_entries(self):
        result = AIMEService._remove_dn_list(["/CN=A", "/CN=B"], ["/CN=A"])
        assert result == ["/CN=B"]

    def test_ignores_non_matching(self):
        result = AIMEService._remove_dn_list(["/CN=A", "/CN=B"], ["/CN=C"])
        assert result == ["/CN=A", "/CN=B"]

    def test_handles_none_existing(self):
        result = AIMEService._remove_dn_list(None, ["/CN=A"])
        assert result == []

    def test_handles_none_to_remove(self):
        result = AIMEService._remove_dn_list(["/CN=A"], None)
        assert result == ["/CN=A"]

    def test_both_none_returns_empty(self):
        result = AIMEService._remove_dn_list(None, None)
        assert result == []

    def test_remove_all_entries(self):
        result = AIMEService._remove_dn_list(["/CN=A", "/CN=B"], ["/CN=A", "/CN=B"])
        assert result == []

    def test_case_sensitive(self):
        """DN list removal is case-sensitive."""
        result = AIMEService._remove_dn_list(["/CN=A"], ["/cn=a"])
        assert result == ["/CN=A"]


# ===========================================================================
# _preserve_or_set_source_site_name
# ===========================================================================

class TestPreserveOrSetSourceSiteName:
    def test_preserves_existing(self):
        result = AIMEService._preserve_or_set_source_site_name("XSEDE", "ACCESS")
        assert result == "XSEDE"

    def test_sets_when_existing_is_none(self):
        result = AIMEService._preserve_or_set_source_site_name(None, "ACCESS")
        assert result == "ACCESS"

    def test_sets_when_existing_is_empty(self):
        result = AIMEService._preserve_or_set_source_site_name("", "ACCESS")
        assert result == "ACCESS"

    def test_returns_none_when_both_empty(self):
        result = AIMEService._preserve_or_set_source_site_name(None, None)
        assert result is None

    def test_strips_whitespace(self):
        result = AIMEService._preserve_or_set_source_site_name("  ", "ACCESS")
        assert result == "ACCESS"


# ===========================================================================
# _site_scoped_first
# ===========================================================================

class TestSiteScopedFirst:
    def test_returns_site_scoped_row(self, db):
        u1 = User(
            name="User XSEDE",
            email="xsede@test.edu",
            person_id="p-001",
            source_site_name="XSEDE",
            is_active=True,
            dn_list=[],
            tags=[],
        )
        u2 = User(
            name="User ACCESS",
            email="access@test.edu",
            person_id="p-001",
            source_site_name="ACCESS",
            is_active=True,
            dn_list=[],
            tags=[],
        )
        db.add_all([u1, u2])
        db.flush()

        query = db.query(User).filter(User.person_id == "p-001")
        result = AIMEService._site_scoped_first(
            query,
            site_field=User.source_site_name,
            site_name="XSEDE",
            allow_other_sites_when_missing=False,
        )
        assert result.source_site_name == "XSEDE"

    def test_falls_back_to_null_site_legacy_row(self, db):
        u = User(
            name="Legacy User",
            email="legacy@test.edu",
            person_id="p-002",
            source_site_name=None,
            is_active=True,
            dn_list=[],
            tags=[],
        )
        db.add(u)
        db.flush()

        query = db.query(User).filter(User.person_id == "p-002")
        result = AIMEService._site_scoped_first(
            query,
            site_field=User.source_site_name,
            site_name="XSEDE",
            allow_other_sites_when_missing=False,
        )
        assert result is not None
        assert result.source_site_name is None

    def test_returns_none_when_no_match_and_not_allowed(self, db):
        u = User(
            name="Other Site User",
            email="other@test.edu",
            person_id="p-003",
            source_site_name="ACCESS",
            is_active=True,
            dn_list=[],
            tags=[],
        )
        db.add(u)
        db.flush()

        query = db.query(User).filter(User.person_id == "p-003")
        result = AIMEService._site_scoped_first(
            query,
            site_field=User.source_site_name,
            site_name="XSEDE",
            allow_other_sites_when_missing=False,
        )
        assert result is None

    def test_returns_other_site_row_when_allowed(self, db):
        u = User(
            name="Other Site",
            email="other2@test.edu",
            person_id="p-004",
            source_site_name="ACCESS",
            is_active=True,
            dn_list=[],
            tags=[],
        )
        db.add(u)
        db.flush()

        query = db.query(User).filter(User.person_id == "p-004")
        result = AIMEService._site_scoped_first(
            query,
            site_field=User.source_site_name,
            site_name="XSEDE",
            allow_other_sites_when_missing=True,
        )
        assert result is not None


# ===========================================================================
# _resolve_project
# ===========================================================================

class TestResolveProject:
    def _make_project(self, db, grant_number, site_project_id=None, site_name="XSEDE"):
        p = Project(
            aime_allocation_id=grant_number,
            name=f"Project {grant_number}",
            grant_number=grant_number,
            site_project_id=site_project_id,
            source_site_name=site_name,
            cpu_allocated=0,
            gpu_allocated=0,
            is_active=True,
            tags=[],
        )
        db.add(p)
        db.flush()
        return p

    def test_resolve_by_site_project_id(self, db, svc):
        p = self._make_project(db, "TG-001", site_project_id="PROJ-001")
        result = svc._resolve_project(
            db, site_project_id="PROJ-001", source_site_name="XSEDE"
        )
        assert result.id == p.id

    def test_resolve_by_grant_number(self, db, svc):
        p = self._make_project(db, "TG-002")
        result = svc._resolve_project(
            db, grant_number="TG-002", source_site_name="XSEDE"
        )
        assert result.id == p.id

    def test_returns_none_when_not_found(self, db, svc):
        result = svc._resolve_project(
            db, grant_number="TG-NONEXISTENT", source_site_name="XSEDE"
        )
        assert result is None

    def test_site_isolation(self, db, svc):
        """A project tagged to ACCESS must not be returned for XSEDE queries."""
        self._make_project(db, "TG-003", site_name="ACCESS")
        result = svc._resolve_project(
            db, grant_number="TG-003", source_site_name="XSEDE"
        )
        assert result is None


# ===========================================================================
# _resolve_user
# ===========================================================================

class TestResolveUser:
    def _make_user(self, db, person_id, email=None, site_name="XSEDE"):
        u = User(
            name=f"User {person_id}",
            email=email,
            person_id=person_id,
            source_site_name=site_name,
            is_active=True,
            dn_list=[],
            tags=[],
        )
        db.add(u)
        db.flush()
        return u

    def test_resolve_by_person_id(self, db, svc):
        u = self._make_user(db, "person-001")
        result = svc._resolve_user(db, person_id="person-001", source_site_name="XSEDE")
        assert result.id == u.id

    def test_resolve_by_email(self, db, svc):
        u = self._make_user(db, "person-002", email="unique@test.edu")
        result = svc._resolve_user(
            db, email="unique@test.edu", source_site_name="OTHER"
        )
        assert result.id == u.id

    def test_returns_none_when_not_found(self, db, svc):
        result = svc._resolve_user(
            db, person_id="nobody", source_site_name="XSEDE"
        )
        assert result is None


# ===========================================================================
# validate_packet_dry_run
# ===========================================================================

class TestValidatePacketDryRun:
    def test_valid_packet_returns_valid_true(self, svc):
        packet = {
            "type": "request_project_create",
            "header": {"packet_rec_id": 1},
            "body": {
                "AllocationType": "new",
                "EndDate": "2027-01-01",
                "GrantNumber": "TG-001",
                "PfosNumber": "1",
                "PiFirstName": "J",
                "PiLastName": "S",
                "PiOrganization": "PSC",
                "PiOrgCode": "1",
                "StartDate": "2026-01-01",
                "ResourceList": ["r.edu"],
                "RecordID": "1",
                "ServiceUnitsAllocated": "1000",
            },
        }
        result = svc.validate_packet_dry_run(packet)
        assert result["valid"] is True
        assert result["packet_type"] == "request_project_create"

    def test_unknown_type_returns_valid_false(self, svc):
        packet = {"type": "not_real", "header": {}, "body": {}}
        result = svc.validate_packet_dry_run(packet)
        assert result["valid"] is False
        assert any(e["kind"] == "unsupported_type" for e in result["errors"])

    def test_invalid_body_returns_valid_false(self, svc):
        packet = {
            "type": "request_project_create",
            "header": {"packet_rec_id": 1},
            "body": {"GrantNumber": "TG-X"},  # missing required fields
        }
        result = svc.validate_packet_dry_run(packet)
        assert result["valid"] is False
        assert len(result["errors"]) > 0
