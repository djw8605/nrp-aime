"""
Shared test fixtures for all backend tests.

Sets DATABASE_URL to an in-memory SQLite instance BEFORE any app imports so
that app.database creates its engine against SQLite rather than Postgres.
All model tables are created once per test session; each individual test gets
a transactional session that is rolled back at teardown.
"""

import os

# Must be set before any app module is imported.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_SECRET_KEY", "test-secret-key")
os.environ.setdefault("AMIE_API_KEY", "test-api-key")

import pytest
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import Session as SASession

from app.database import Base

# Import every model so they register themselves with Base.metadata.
import app.models.amie_packet  # noqa: F401
import app.models.amie_allocation_packet  # noqa: F401
import app.models.amie_new_user_packet  # noqa: F401
import app.models.amie_lifecycle_packet  # noqa: F401
import app.models.amie_unprocessed_packet  # noqa: F401
import app.models.amie_usage_export  # noqa: F401
import app.models.project  # noqa: F401
import app.models.project_user  # noqa: F401
import app.models.user  # noqa: F401
import app.models.project_invite  # noqa: F401
import app.models.project_invite_event  # noqa: F401
import app.models.outbound_packet_log  # noqa: F401
import app.models.project_usage_snapshot  # noqa: F401
import app.models.worker_status  # noqa: F401
import app.models.alert_notification  # noqa: F401

SQLITE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """Create a single SQLite engine for the entire test session."""
    _engine = create_engine(SQLITE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(_engine)
    yield _engine
    Base.metadata.drop_all(_engine)
    _engine.dispose()


@pytest.fixture
def db(engine):
    """
    Transactional DB session using SAVEPOINTs (SQLAlchemy 2.0+).

    Opens a connection and issues an explicit ``BEGIN`` to SQLite so that the
    full transaction is visible at the DBAPI level.  The session is created with
    ``join_transaction_mode="create_savepoint"`` so every ``session.commit()``
    call inside the code under test only releases a SAVEPOINT – it does NOT
    touch the outer transaction.  At teardown the outer transaction is rolled
    back via ``ROLLBACK``, leaving the database clean for the next test.

    Note: ``conn.exec_driver_sql("BEGIN")`` is required because SQLAlchemy's
    lazy ``conn.begin()`` does not actually issue ``BEGIN`` to SQLite;
    the SAVEPOINT would otherwise be issued outside any wrapping transaction
    and the subsequent ``ROLLBACK`` would be a no-op.
    """
    connection = engine.connect()
    connection.exec_driver_sql("BEGIN")
    session = SASession(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    connection.exec_driver_sql("ROLLBACK")
    connection.close()


@pytest.fixture
def mock_amie_client(mocker):
    """Mock of amieclient.AMIEClient with context-manager support."""
    client = mocker.MagicMock()
    client.__enter__ = mocker.MagicMock(return_value=client)
    client.__exit__ = mocker.MagicMock(return_value=False)
    # Sensible default for send_packet
    send_result = mocker.MagicMock()
    send_result.as_dict.return_value = {"header": {"packet_rec_id": 9999}}
    client.send_packet.return_value = send_result
    return client


@pytest.fixture
def mock_authentik(mocker):
    """Mock of AuthentikService; every method returns success by default."""
    svc = mocker.MagicMock()
    svc.ensure_user_in_project.return_value = {"ok": True}
    svc.remove_user_from_project.return_value = {"ok": True}
    return svc


@pytest.fixture
def mock_kubernetes(mocker):
    """Mock of KubernetesProvisioningService."""
    svc = mocker.MagicMock()
    svc.ensure_user_project_access.return_value = {"ok": True}
    svc.remove_user_project_access.return_value = {"ok": True}
    return svc


@pytest.fixture
def mock_provisioning(mocker):
    """Mock of ProjectProvisioningService."""
    svc = mocker.MagicMock()
    svc.mark_received.return_value = True
    return svc


@pytest.fixture(autouse=True)
def mock_alert_service():
    """
    Auto-mock AlertService.send for all tests.

    AlertService queries alert_notifications rows whose last_sent_at comes back
    as a timezone-naive datetime from SQLite, which causes a TypeError when
    compared to timezone-aware datetime.now(UTC).  Since alert side-effects are
    not the subject of these tests we suppress them globally.
    """
    with patch("app.services.alerts.AlertService.send", return_value=None):
        yield


@pytest.fixture
def aime_service(mock_authentik, mock_kubernetes, mock_provisioning):
    """AIMEService wired with mocked external dependencies."""
    from app.services.aime.service import AIMEService

    return AIMEService(
        site_name="test-site",
        authentik_service=mock_authentik,
        kubernetes_service=mock_kubernetes,
        project_provisioning_service=mock_provisioning,
    )


# ---------------------------------------------------------------------------
# Packet dict factories
# ---------------------------------------------------------------------------

def make_header(packet_rec_id: int = 1001, **kwargs) -> dict:
    return {
        "packet_rec_id": packet_rec_id,
        "trans_rec_id": kwargs.get("trans_rec_id", 2001),
        "packet_id": kwargs.get("packet_id", 3001),
        "transaction_id": kwargs.get("transaction_id", 4001),
        "local_site_name": kwargs.get("local_site_name", "test-site"),
        "remote_site_name": kwargs.get("remote_site_name", "XSEDE"),
        "originating_site_name": kwargs.get("originating_site_name", "XSEDE"),
        "transaction_state": kwargs.get("transaction_state", "in-progress"),
        "packet_state": kwargs.get("packet_state", ""),
    }


def make_rpc_packet(packet_rec_id: int = 1001, **body_overrides) -> dict:
    """Minimal valid request_project_create packet dict."""
    body = {
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
    body.update(body_overrides)
    return {
        "type": "request_project_create",
        "header": make_header(packet_rec_id),
        "body": body,
    }


def make_rac_packet(
    packet_rec_id: int = 1002,
    grant_number: str = "TG-TEST001",
    **body_overrides,
) -> dict:
    """Minimal valid request_account_create packet dict."""
    body = {
        "GrantNumber": grant_number,
        "ResourceList": ["supercomputer.test.edu"],
        "UserFirstName": "Ada",
        "UserLastName": "Lovelace",
        "UserOrganization": "PSC",
        "UserOrgCode": "99999",
        "UserPersonID": "person-ada-001",
        "UserEmail": "ada@test.edu",
    }
    body.update(body_overrides)
    return {
        "type": "request_account_create",
        "header": make_header(packet_rec_id),
        "body": body,
    }


def make_lifecycle_packet(
    packet_type: str,
    packet_rec_id: int = 1010,
    **body_overrides,
) -> dict:
    """Generic lifecycle packet (inactivate / reactivate / notify / etc.)."""
    body = {
        "GrantNumber": "TG-TEST001",
        "ProjectID": "PROJ-001",
        "PersonID": "person-ada-001",
        "ResourceList": ["supercomputer.test.edu"],
    }
    body.update(body_overrides)
    return {
        "type": packet_type,
        "header": make_header(packet_rec_id),
        "body": body,
    }
