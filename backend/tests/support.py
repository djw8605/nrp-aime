"""Shared test helpers for AMIE packet processing and lifecycle tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.database import Base
from app.models.project import Project


def create_test_session() -> tuple[Any, Session]:
    """Create an isolated in-memory database session for one test."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False)()
    return engine, session


class TrackingAuthentikService:
    """Simple stub for Authentik interactions."""

    def __init__(self) -> None:
        self.ensure_calls: list[dict[str, Any]] = []
        self.remove_calls: list[dict[str, Any]] = []

    def ensure_user_in_project(self, **kwargs: Any) -> dict[str, Any]:
        self.ensure_calls.append(kwargs)
        return {"ok": True}

    def remove_user_from_project(self, **kwargs: Any) -> dict[str, Any]:
        self.remove_calls.append(kwargs)
        return {"ok": True}


class TrackingKubernetesService:
    """Simple stub for namespace access operations."""

    def __init__(self) -> None:
        self.ensure_calls: list[dict[str, Any]] = []
        self.remove_calls: list[dict[str, Any]] = []

    def ensure_user_project_access(self, **kwargs: Any) -> dict[str, Any]:
        self.ensure_calls.append(kwargs)
        return {"ok": True}

    def remove_user_project_access(self, **kwargs: Any) -> dict[str, Any]:
        self.remove_calls.append(kwargs)
        return {"ok": True}


class TrackingProjectProvisioningService:
    """Stub provisioning service used to avoid external side effects in tests."""

    def __init__(self) -> None:
        self.received_calls: list[dict[str, Any]] = []
        self.alert_calls: list[dict[str, Any]] = []

    def mark_received(self, db: Session, *, project: Project, reason: str) -> bool:  # noqa: ARG002
        project.provisioning_state = Project.PROVISIONING_STATE_RECEIVED
        self.received_calls.append({"project_id": project.id, "reason": reason})
        return True

    def emit_required_alert(
        self,
        db: Session,
        *,
        project: Project,
        reason: str,
    ) -> None:  # noqa: ARG002
        self.alert_calls.append({"project_id": project.id, "reason": reason})


def packet_header(packet_rec_id: int, **overrides: Any) -> dict[str, Any]:
    """Build a standard AMIE packet header for tests."""
    header = {
        "packet_rec_id": packet_rec_id,
        "trans_rec_id": packet_rec_id + 1000,
        "packet_id": packet_rec_id + 2000,
        "transaction_id": packet_rec_id + 3000,
        "remote_site_name": "ACCESS",
        "local_site_name": "NRP",
        "originating_site_name": "ACCESS",
        "outgoing_flag": False,
        "packet_timestamp": "2026-03-24T12:00:00Z",
        "client_state": "in-progress",
        "packet_state": "in-progress",
        "transaction_state": "in-progress",
    }
    header.update(overrides)
    return header


def request_project_create_packet(packet_rec_id: int = 1001, **body_overrides: Any) -> dict[str, Any]:
    """Build a doc-shaped ``request_project_create`` packet."""
    body = {
        "AllocationType": "New",
        "AllocatedResource": "cluster.example.org",
        "EndDate": "2026-12-31",
        "GrantNumber": "TG-TEST123",
        "PfosNumber": "12345",
        "PiDnList": ["/C=US/O=Example/CN=Pat Investigator"],
        "PiEmail": "pi@example.org",
        "PiFirstName": "Pat",
        "PiLastName": "Investigator",
        "PiOrgCode": "T000001",
        "PiOrganization": "Example University",
        "PiPersonID": "PI-001",
        "PiRequestedLoginList": ["pi-login"],
        "ProjectID": "PROJECT-001",
        "ProjectTitle": "ACCESS Project",
        "RecordID": "XRAS-100001-cluster.example.org",
        "ResourceList": ["cluster.example.org"],
        "RoleList": ["pi"],
        "ServiceUnitsAllocated": "500",
        "ServiceUnitsRemaining": "500",
        "SitePersonId": [{"PersonID": "pi-local", "Site": "X-PORTAL"}],
        "StartDate": "2026-01-01",
    }
    body.update(body_overrides)
    return {
        "type": "request_project_create",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def request_account_create_packet(packet_rec_id: int = 2001, **body_overrides: Any) -> dict[str, Any]:
    """Build a doc-shaped ``request_account_create`` packet."""
    body = {
        "AllocatedResource": "cluster.example.org",
        "GrantNumber": "TG-TEST123",
        "ProjectID": "PROJECT-001",
        "ResourceList": ["cluster.example.org"],
        "RoleList": ["member"],
        "ServiceUnitsAllocated": "250",
        "ServiceUnitsRemaining": "250",
        "SitePersonId": [{"PersonID": "member-local", "Site": "X-PORTAL"}],
        "UserDnList": ["/C=US/O=Example/CN=Taylor Member"],
        "UserEmail": "member@example.org",
        "UserFirstName": "Taylor",
        "UserGlobalID": "GLOBAL-2001",
        "UserLastName": "Member",
        "UserOrgCode": "T000002",
        "UserOrganization": "Example University",
        "UserPersonID": "USER-2001",
        "UserRequestedLoginList": ["member-login"],
    }
    body.update(body_overrides)
    return {
        "type": "request_account_create",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def data_project_create_packet(packet_rec_id: int = 3001, **body_overrides: Any) -> dict[str, Any]:
    """Build a ``data_project_create`` packet."""
    body = {
        "DnList": ["/C=US/O=Example/CN=Pat Investigator"],
        "GlobalID": "GLOBAL-PI-001",
        "PersonID": "PI-001",
        "ProjectID": "PROJECT-001",
    }
    body.update(body_overrides)
    return {
        "type": "data_project_create",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def data_account_create_packet(packet_rec_id: int = 3101, **body_overrides: Any) -> dict[str, Any]:
    """Build a ``data_account_create`` packet."""
    body = {
        "DnList": ["/C=US/O=Example/CN=Taylor Member"],
        "GlobalID": "GLOBAL-2001",
        "PersonID": "USER-2001",
        "ProjectID": "PROJECT-001",
    }
    body.update(body_overrides)
    return {
        "type": "data_account_create",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def request_project_inactivate_packet(
    packet_rec_id: int = 8001,
    **body_overrides: Any,
) -> dict[str, Any]:
    """Build a ``request_project_inactivate`` packet."""
    body = {
        "AllocatedResource": "cluster.example.org",
        "Comment": "suspend project",
        "GrantNumber": "TG-TEST123",
        "ProjectID": "PROJECT-001",
        "ResourceList": ["cluster.example.org"],
    }
    body.update(body_overrides)
    return {
        "type": "request_project_inactivate",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def request_project_reactivate_packet(
    packet_rec_id: int = 9001,
    **body_overrides: Any,
) -> dict[str, Any]:
    """Build a ``request_project_reactivate`` packet."""
    body = {
        "AllocatedResource": "cluster.example.org",
        "Comment": "resume project",
        "GrantNumber": "TG-TEST123",
        "ProjectID": "PROJECT-001",
        "ResourceList": ["cluster.example.org"],
    }
    body.update(body_overrides)
    return {
        "type": "request_project_reactivate",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def request_account_inactivate_packet(
    packet_rec_id: int = 4001,
    **body_overrides: Any,
) -> dict[str, Any]:
    """Build a ``request_account_inactivate`` packet."""
    body = {
        "AllocatedResource": "cluster.example.org",
        "Comment": "remove access",
        "PersonID": "USER-2001",
        "ProjectID": "PROJECT-001",
        "ResourceList": ["cluster.example.org"],
    }
    body.update(body_overrides)
    return {
        "type": "request_account_inactivate",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def request_account_reactivate_packet(
    packet_rec_id: int = 5001,
    **body_overrides: Any,
) -> dict[str, Any]:
    """Build a ``request_account_reactivate`` packet."""
    body = {
        "AllocatedResource": "cluster.example.org",
        "Comment": "restore access",
        "PersonID": "USER-2001",
        "ProjectID": "PROJECT-001",
        "ResourceList": ["cluster.example.org"],
    }
    body.update(body_overrides)
    return {
        "type": "request_account_reactivate",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def request_user_modify_packet(packet_rec_id: int = 6001, **body_overrides: Any) -> dict[str, Any]:
    """Build a ``request_user_modify`` packet."""
    body = {
        "ActionType": "replace",
        "DnList": ["/C=US/O=Example/CN=Taylor Member Updated"],
        "Email": "member-updated@example.org",
        "FirstName": "Taylor",
        "LastName": "Member-Updated",
        "Organization": "Updated University",
        "OrgCode": "T999999",
        "PersonID": "USER-2001",
    }
    body.update(body_overrides)
    return {
        "type": "request_user_modify",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


def inform_transaction_complete_packet(
    packet_rec_id: int = 7001,
    **body_overrides: Any,
) -> dict[str, Any]:
    """Build an ``inform_transaction_complete`` packet."""
    body = {
        "DetailCode": 1,
        "Message": "Transaction completed",
        "StatusCode": "Success",
    }
    body.update(body_overrides)
    return {
        "type": "inform_transaction_complete",
        "header": packet_header(packet_rec_id),
        "body": body,
    }


class FakeReplyPacket:
    """Reply packet object that supports attribute assignment."""

    def __init__(self, packet_type: str) -> None:
        self.packet_type = packet_type


class FakeSourcePacket:
    """Source packet returned by the fake AMIE client."""

    def __init__(self, packet_type: str, body: dict[str, Any]) -> None:
        self.type = packet_type
        self.body = SimpleNamespace(**body)
        self._body = dict(body)

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "body": dict(self._body)}

    def reply_packet(self, packet_type: str) -> FakeReplyPacket:
        return FakeReplyPacket(packet_type)


class FakeSendResult:
    """Outbound send result with AMIE-like header data."""

    def __init__(self, packet_rec_id: int, transaction_id: int) -> None:
        self.packet_rec_id = packet_rec_id
        self.transaction_id = transaction_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "header": {
                "packet_rec_id": self.packet_rec_id,
                "transaction_id": self.transaction_id,
            }
        }


class FakeAMIEClient:
    """In-memory AMIE client stub used by lifecycle reconciliation tests."""

    instances: list["FakeAMIEClient"] = []
    sent_packets: list[FakeReplyPacket] = []
    source_packets: dict[int, FakeSourcePacket] = {}
    # Number of upcoming send_packet calls that should raise.
    send_failures: int = 0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.last_outbound_packet_rec_id: int | None = None
        type(self).instances.append(self)

    def __enter__(self) -> "FakeAMIEClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        return False

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
        cls.sent_packets = []
        cls.source_packets = {}
        cls.send_failures = 0

    def get_packet(self, *, packet_rec_id: int) -> Any:
        if packet_rec_id in type(self).source_packets:
            return type(self).source_packets[packet_rec_id]
        if packet_rec_id == self.last_outbound_packet_rec_id:
            return {
                "header": {
                    "packet_state": "processed",
                    "transaction_state": "complete",
                }
            }
        raise AssertionError(f"Unexpected packet_rec_id requested: {packet_rec_id}")

    def send_packet(self, packet: FakeReplyPacket) -> FakeSendResult:
        if type(self).send_failures > 0:
            type(self).send_failures -= 1
            raise RuntimeError("simulated AMIE send failure")
        type(self).sent_packets.append(packet)
        outbound_packet_rec_id = 90000 + len(type(self).sent_packets)
        self.last_outbound_packet_rec_id = outbound_packet_rec_id
        return FakeSendResult(
            packet_rec_id=outbound_packet_rec_id,
            transaction_id=80000 + len(type(self).sent_packets),
        )
