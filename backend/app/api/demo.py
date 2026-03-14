"""Demo packet API endpoints for local interface testing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.amie_packet import AMIEPacket
from app.services.aime.service import AIMEService

router = APIRouter()


class DemoPacketRequest(BaseModel):
    """Payload for demo packet generation."""

    scenario: Literal["project_and_account", "project_only", "account_only"] = (
        "project_and_account"
    )


@router.post("/send")
def send_demo_packet(
    payload: DemoPacketRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Generate and ingest demo AMIE packet(s)."""
    now = datetime.now(UTC)
    suffix = now.strftime("%Y%m%d%H%M%S%f")

    max_packet_rec_id = db.query(func.coalesce(func.max(AMIEPacket.packet_rec_id), 0)).scalar()
    base_packet_rec_id = int(max_packet_rec_id or 0) + 1

    trans_rec_id = base_packet_rec_id + 100_000
    transaction_id = base_packet_rec_id + 200_000

    grant_number = f"DEMO-GRANT-{suffix}"
    allocation_record_id = f"DEMO-RECORD-{suffix}"
    project_id = f"demo-project-{suffix}"
    resource = "demo.resource.nrp-nautilus.io"

    pi_person_id = f"demo-pi-{suffix}"
    user_person_id = f"demo-user-{suffix}"

    site_name = settings.amie_site_name or "NRP"

    def build_header(packet_rec_id: int) -> dict:
        return {
            "packet_rec_id": packet_rec_id,
            "trans_rec_id": trans_rec_id,
            "packet_id": packet_rec_id,
            "transaction_id": transaction_id,
            "local_site_name": "XSEDE",
            "remote_site_name": site_name,
            "originating_site_name": "XSEDE",
            "outgoing_flag": False,
            "transaction_state": "in_progress",
            "packet_state": "new",
            "packet_timestamp": now.isoformat(),
            "client_state": None,
        }

    rpc = {
        "type": "request_project_create",
        "header": build_header(base_packet_rec_id),
        "body": {
            "AllocationType": "new",
            "EndDate": (now + timedelta(days=90)).date().isoformat(),
            "GrantNumber": grant_number,
            "PfosNumber": "DEMO-001",
            "PiFirstName": "Demo",
            "PiLastName": "PI",
            "PiOrganization": "NRP Demo Org",
            "PiOrgCode": "NRP",
            "StartDate": now.date().isoformat(),
            "ResourceList": [resource],
            "RecordID": allocation_record_id,
            "ServiceUnitsAllocated": "1000",
            "ProjectID": project_id,
            "ProjectTitle": f"Demo Project {suffix}",
            "RequestType": "new",
            "PiPersonID": pi_person_id,
            "PiEmail": f"demo-pi-{suffix}@example.org",
            "RoleList": ["pi"],
        },
    }

    rac = {
        "type": "request_account_create",
        "header": build_header(base_packet_rec_id + 1),
        "body": {
            "GrantNumber": grant_number,
            "ProjectID": project_id,
            "ResourceList": [resource],
            "UserFirstName": "Demo",
            "UserLastName": "User",
            "UserOrganization": "NRP Demo Org",
            "UserOrgCode": "NRP",
            "UserPersonID": user_person_id,
            "UserEmail": f"demo-user-{suffix}@example.org",
            "UserRemoteSiteLogin": f"demouser{suffix[-6:]}",
            "RoleList": ["member"],
        },
    }

    packets: list[dict] = []
    if payload.scenario in ("project_and_account", "project_only"):
        packets.append(rpc)
    if payload.scenario in ("project_and_account", "account_only"):
        packets.append(rac)

    aime_svc = AIMEService(site_name=site_name)
    handled = 0
    project_names: list[str] = []

    for packet in packets:
        result = aime_svc.ingest_packet(db, packet)
        if result.handled:
            handled += 1
        if result.project is not None and result.project.name not in project_names:
            project_names.append(result.project.name)

    return {
        "message": f"Injected {handled} demo packet(s)",
        "scenario": payload.scenario,
        "packet_count": len(packets),
        "handled": handled,
        "trans_rec_id": trans_rec_id,
        "transaction_id": transaction_id,
        "project_id": project_id,
        "grant_number": grant_number,
        "projects": project_names,
    }
