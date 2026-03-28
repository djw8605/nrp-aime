"""AIME packet ingestion service.

Wraps the ``amieclient`` library and translates incoming AMIE packets into
database records (Projects, Users, account membership rows, and packet logs).
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.amie_allocation_packet import AMIEAllocationPacket
from app.models.amie_lifecycle_packet import AMIELifecyclePacket
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.amie_packet import AMIEPacket
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.authentik.service import AuthentikService
from app.services.alerts import AlertService
from app.services.aime.bindings import (
    DataAccountCreatePacketBinding,
    DataProjectCreatePacketBinding,
    InformTransactionCompletePacketBinding,
    NotifyAccountCreatePacketBinding,
    NotifyAccountInactivatePacketBinding,
    NotifyAccountReactivatePacketBinding,
    NotifyProjectCreatePacketBinding,
    NotifyProjectInactivatePacketBinding,
    NotifyProjectReactivatePacketBinding,
    RequestAccountCreateBodyBinding,
    RequestAccountCreatePacketBinding,
    RequestAccountInactivatePacketBinding,
    RequestAccountReactivatePacketBinding,
    RequestPersonMergePacketBinding,
    RequestProjectCreateBodyBinding,
    RequestProjectCreatePacketBinding,
    RequestProjectInactivatePacketBinding,
    RequestProjectReactivatePacketBinding,
    RequestUserModifyPacketBinding,
    UnsupportedPacketType,
    bind_packet,
    coerce_packet_dict,
)
from app.services.observability import ObservabilityService
from app.services.kubernetes.service import KubernetesProvisioningService
from app.services.project_provisioning import ProjectProvisioningService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestResult:
    """Result for one packet ingestion attempt."""

    handled: bool
    packet_type: str
    project: Project | None = None


class AIMEService:
    """Translates AMIE packets into database records."""

    def __init__(
        self,
        site_name: str,
        authentik_service: AuthentikService | None = None,
        kubernetes_service: KubernetesProvisioningService | None = None,
        project_provisioning_service: ProjectProvisioningService | None = None,
    ) -> None:
        self.site_name = site_name
        self.authentik_service = authentik_service or AuthentikService()
        self.kubernetes_service = (
            kubernetes_service or KubernetesProvisioningService()
        )
        self.project_provisioning = project_provisioning_service or ProjectProvisioningService(
            kubernetes_service=self.kubernetes_service,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _full_name(
        first_name: str | None, middle_name: str | None, last_name: str | None
    ) -> str:
        return " ".join(
            part.strip()
            for part in [first_name, middle_name, last_name]
            if part and part.strip()
        ).strip()

    @staticmethod
    def _to_date(value: date | datetime | None) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        return value

    @staticmethod
    def _to_decimal(value: Any) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)

    def _json_compatible(self, data: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(data, default=self._json_default))

    def _packet_site_name(self, packet_record: AMIEPacket) -> str:
        for candidate in (
            packet_record.remote_site_name,
            packet_record.originating_site_name,
            packet_record.local_site_name,
            self.site_name,
        ):
            value = str(candidate or "").strip()
            if value:
                return value
        return self.site_name

    @staticmethod
    def _merge_dn_list(
        existing: list[str] | None,
        incoming: list[str] | None,
    ) -> list[str]:
        merged: list[str] = []
        for dn_raw in [*(existing or []), *(incoming or [])]:
            dn = (dn_raw or "").strip()
            if dn and dn not in merged:
                merged.append(dn)
        return merged

    @staticmethod
    def _remove_dn_list(existing: list[str] | None, to_remove: list[str] | None) -> list[str]:
        current = [(dn or "").strip() for dn in (existing or []) if (dn or "").strip()]
        remove = {(dn or "").strip() for dn in (to_remove or []) if (dn or "").strip()}
        return [dn for dn in current if dn not in remove]

    @staticmethod
    def _site_scoped_first(
        query,
        *,
        site_field,
        site_name: str | None,
        allow_other_sites_when_missing: bool,
    ):
        """Return site-matched row first, then legacy null-site row when present.

        If ``allow_other_sites_when_missing`` is False and no site/legacy row matches,
        return ``None`` instead of crossing into another site's row.
        """
        if not site_name:
            return query.first()

        scoped = query.filter(site_field == site_name).first()
        if scoped is not None:
            return scoped

        legacy = query.filter(or_(site_field.is_(None), site_field == "")).first()
        if legacy is not None:
            return legacy

        if allow_other_sites_when_missing:
            return query.first()
        return None

    @staticmethod
    def _preserve_or_set_source_site_name(
        existing: str | None,
        incoming: str | None,
    ) -> str | None:
        """Set source site only when unset, preserving existing tagged records."""
        existing_clean = str(existing or "").strip()
        incoming_clean = str(incoming or "").strip()
        if existing_clean:
            return existing_clean
        return incoming_clean or None

    def _resolve_project(
        self,
        db: Session,
        *,
        grant_number: str | None = None,
        site_project_id: str | None = None,
        allocation_record_id: str | None = None,
        source_site_name: str | None = None,
    ) -> Project | None:
        site_name = (source_site_name or "").strip() or None
        if site_project_id:
            query = db.query(Project).filter(Project.site_project_id == site_project_id)
            project = self._site_scoped_first(
                query,
                site_field=Project.source_site_name,
                site_name=site_name,
                allow_other_sites_when_missing=False,
            )
            if project is not None:
                return project
        if grant_number:
            query = db.query(Project).filter(Project.grant_number == grant_number)
            project = self._site_scoped_first(
                query,
                site_field=Project.source_site_name,
                site_name=site_name,
                allow_other_sites_when_missing=False,
            )
            if project is not None:
                return project
        if allocation_record_id:
            query = db.query(Project).filter(
                Project.allocation_record_id == allocation_record_id
            )
            return self._site_scoped_first(
                query,
                site_field=Project.source_site_name,
                site_name=site_name,
                allow_other_sites_when_missing=False,
            )
        return None

    def _resolve_user(
        self,
        db: Session,
        *,
        person_id: str | None = None,
        email: str | None = None,
        global_id: str | None = None,
        source_site_name: str | None = None,
    ) -> User | None:
        site_name = (source_site_name or "").strip() or None
        if person_id:
            query = db.query(User).filter(User.person_id == person_id)
            user = self._site_scoped_first(
                query,
                site_field=User.source_site_name,
                site_name=site_name,
                allow_other_sites_when_missing=False,
            )
            if user is not None:
                return user
        if email:
            query = db.query(User).filter(User.email == email)
            user = self._site_scoped_first(
                query,
                site_field=User.source_site_name,
                site_name=site_name,
                allow_other_sites_when_missing=True,
            )
            if user is not None:
                return user
        if global_id:
            query = db.query(User).filter(User.global_id == global_id)
            user = self._site_scoped_first(
                query,
                site_field=User.source_site_name,
                site_name=site_name,
                allow_other_sites_when_missing=True,
            )
            if user is not None:
                return user
        return None

    def _get_or_create_user_by_person_id(
        self,
        db: Session,
        *,
        person_id: str,
        default_name: str | None = None,
        global_id: str | None = None,
        source_site_name: str | None = None,
    ) -> User:
        user = self._resolve_user(
            db,
            person_id=person_id,
            global_id=global_id,
            source_site_name=source_site_name,
        )
        if user is not None:
            if global_id and not user.global_id:
                user.global_id = global_id
            user.source_site_name = self._preserve_or_set_source_site_name(
                user.source_site_name,
                source_site_name,
            )
            return user

        user = User(
            person_id=person_id,
            global_id=global_id,
            name=default_name or person_id,
            source_site_name=source_site_name,
            is_active=True,
            dn_list=[],
        )
        db.add(user)
        db.flush()
        logger.info("Created placeholder user for PersonID=%s", person_id)
        return user

    def _refresh_user_active_from_accounts(self, db: Session, user: User) -> None:
        has_active_account = (
            db.query(ProjectUser.id)
            .filter(ProjectUser.user_id == user.id, ProjectUser.is_active.is_(True))
            .first()
            is not None
        )
        user.is_active = has_active_account or bool(user.dn_list)

    def _get_or_create_user_from_pi(
        self,
        db: Session,
        body: RequestProjectCreateBodyBinding,
        *,
        source_site_name: str | None = None,
    ) -> User:
        """Return an existing PI user or create a new one."""
        full_name = self._full_name(body.PiFirstName, body.PiMiddleName, body.PiLastName)
        user = self._resolve_user(
            db,
            person_id=body.PiPersonID,
            email=body.PiEmail,
            source_site_name=source_site_name,
        )
        if user is None:
            user = User(
                email=body.PiEmail,
                name=full_name or body.PiOrganization or (body.PiPersonID or "Unknown PI"),
                first_name=body.PiFirstName,
                middle_name=body.PiMiddleName,
                last_name=body.PiLastName,
                person_id=body.PiPersonID,
                organization=body.PiOrganization,
                org_code=body.PiOrgCode,
                department=body.PiDepartment,
                nsf_status_code=body.NsfStatusCode,
                source_site_name=source_site_name,
                dn_list=self._merge_dn_list([], body.PiDnList),
                is_active=True,
            )
            db.add(user)
            db.flush()
            logger.info("Created PI user from packet: %s", full_name or body.PiPersonID)
            return user

        user.name = full_name or user.name
        user.first_name = body.PiFirstName or user.first_name
        user.middle_name = body.PiMiddleName or user.middle_name
        user.last_name = body.PiLastName or user.last_name
        user.person_id = body.PiPersonID or user.person_id
        user.email = body.PiEmail or user.email
        user.organization = body.PiOrganization or user.organization
        user.org_code = body.PiOrgCode or user.org_code
        user.department = body.PiDepartment or user.department
        user.nsf_status_code = body.NsfStatusCode or user.nsf_status_code
        user.source_site_name = self._preserve_or_set_source_site_name(
            user.source_site_name,
            source_site_name,
        )
        user.dn_list = self._merge_dn_list(user.dn_list, body.PiDnList)
        user.is_active = True
        return user

    def _get_or_create_user_from_account(
        self,
        db: Session,
        body: RequestAccountCreateBodyBinding,
        *,
        source_site_name: str | None = None,
    ) -> User:
        """Return an existing user from request_account_create or create one."""
        full_name = self._full_name(
            body.UserFirstName, body.UserMiddleName, body.UserLastName
        )
        user = self._resolve_user(
            db,
            person_id=body.UserPersonID,
            email=body.UserEmail,
            global_id=body.UserGlobalID,
            source_site_name=source_site_name,
        )
        service_units = self._to_decimal(body.ServiceUnitsAllocated)
        if user is None:
            user = User(
                email=body.UserEmail,
                name=full_name or body.UserOrganization or (body.UserPersonID or "Unknown User"),
                first_name=body.UserFirstName,
                middle_name=body.UserMiddleName,
                last_name=body.UserLastName,
                person_id=body.UserPersonID,
                global_id=body.UserGlobalID,
                organization=body.UserOrganization,
                org_code=body.UserOrgCode,
                department=body.UserDepartment,
                nsf_status_code=body.NsfStatusCode,
                source_site_name=source_site_name,
                service_units_allocated=service_units,
                dn_list=self._merge_dn_list([], body.UserDnList),
                remote_site_login=body.UserRemoteSiteLogin,
                is_active=True,
            )
            db.add(user)
            db.flush()
            logger.info("Created new user from packet: %s", full_name or body.UserPersonID)
            return user

        user.name = full_name or user.name
        user.first_name = body.UserFirstName or user.first_name
        user.middle_name = body.UserMiddleName or user.middle_name
        user.last_name = body.UserLastName or user.last_name
        user.person_id = body.UserPersonID or user.person_id
        user.global_id = body.UserGlobalID or user.global_id
        user.email = body.UserEmail or user.email
        user.organization = body.UserOrganization or user.organization
        user.org_code = body.UserOrgCode or user.org_code
        user.department = body.UserDepartment or user.department
        user.nsf_status_code = body.NsfStatusCode or user.nsf_status_code
        user.source_site_name = self._preserve_or_set_source_site_name(
            user.source_site_name,
            source_site_name,
        )
        user.dn_list = self._merge_dn_list(user.dn_list, body.UserDnList)
        user.remote_site_login = body.UserRemoteSiteLogin or user.remote_site_login
        if service_units is not None:
            user.service_units_allocated = service_units
        user.is_active = True
        return user

    def _upsert_project_from_allocation(
        self,
        db: Session,
        body: RequestProjectCreateBodyBinding,
        *,
        source_site_name: str | None = None,
    ) -> Project:
        """Create/update project metadata from request_project_create."""
        allocation_record_id = (
            str(body.RecordID).strip() if body.RecordID is not None else None
        ) or None
        project = self._resolve_project(
            db,
            grant_number=body.GrantNumber,
            site_project_id=body.ProjectID,
            allocation_record_id=allocation_record_id,
            source_site_name=source_site_name,
        )
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        if project is None:
            project = Project(
                aime_allocation_id=allocation_record_id or body.GrantNumber,
                name=body.ProjectTitle or body.GrantNumber,
                grant_number=body.GrantNumber,
                allocation_record_id=allocation_record_id,
                site_project_id=body.ProjectID,
                allocation_type=body.AllocationType,
                request_type=body.RequestType,
                source_site_name=source_site_name,
                allocated_resource=body.AllocatedResource,
                service_units_allocated=self._to_decimal(body.ServiceUnitsAllocated),
                service_units_remaining=self._to_decimal(body.ServiceUnitsRemaining),
                start_date=self._to_date(body.StartDate),
                end_date=self._to_date(body.EndDate),
                project_title=body.ProjectTitle,
                pfos_number=body.PfosNumber,
                board_type=body.BoardType,
                pi_person_id=body.PiPersonID,
                pi_first_name=body.PiFirstName,
                pi_middle_name=body.PiMiddleName,
                pi_last_name=body.PiLastName,
                pi_email=body.PiEmail,
                pi_organization=body.PiOrganization,
                pi_org_code=body.PiOrgCode,
                pi_department=body.PiDepartment,
                pi_business_phone_number=body.PiBusinessPhoneNumber,
                resource_type=resource,
                cpu_allocated=0,
                gpu_allocated=0,
                is_active=True,
            )
            db.add(project)
            db.flush()
            logger.info("Created project for grant %s", body.GrantNumber)
            return project

        project.aime_allocation_id = allocation_record_id or project.aime_allocation_id
        project.name = body.ProjectTitle or project.name
        project.grant_number = body.GrantNumber or project.grant_number
        project.allocation_record_id = allocation_record_id or project.allocation_record_id
        project.site_project_id = body.ProjectID or project.site_project_id
        project.allocation_type = body.AllocationType or project.allocation_type
        project.request_type = body.RequestType or project.request_type
        project.source_site_name = self._preserve_or_set_source_site_name(
            project.source_site_name,
            source_site_name,
        )
        project.allocated_resource = body.AllocatedResource or project.allocated_resource
        new_service_units = self._to_decimal(body.ServiceUnitsAllocated)
        if new_service_units is not None:
            project.service_units_allocated = new_service_units
        new_service_units_remaining = self._to_decimal(body.ServiceUnitsRemaining)
        if new_service_units_remaining is not None:
            project.service_units_remaining = new_service_units_remaining
        project.start_date = self._to_date(body.StartDate) or project.start_date
        project.end_date = self._to_date(body.EndDate) or project.end_date
        project.project_title = body.ProjectTitle or project.project_title
        project.pfos_number = body.PfosNumber or project.pfos_number
        project.board_type = body.BoardType or project.board_type
        project.pi_person_id = body.PiPersonID or project.pi_person_id
        project.pi_first_name = body.PiFirstName or project.pi_first_name
        project.pi_middle_name = body.PiMiddleName or project.pi_middle_name
        project.pi_last_name = body.PiLastName or project.pi_last_name
        project.pi_email = body.PiEmail or project.pi_email
        project.pi_organization = body.PiOrganization or project.pi_organization
        project.pi_org_code = body.PiOrgCode or project.pi_org_code
        project.pi_department = body.PiDepartment or project.pi_department
        project.pi_business_phone_number = (
            body.PiBusinessPhoneNumber or project.pi_business_phone_number
        )
        project.resource_type = resource or project.resource_type
        project.is_active = True
        return project

    def _upsert_project_from_account(
        self,
        db: Session,
        body: RequestAccountCreateBodyBinding,
        *,
        source_site_name: str | None = None,
    ) -> Project:
        """Ensure account packets can always bind to a project row."""
        project = self._resolve_project(
            db,
            grant_number=body.GrantNumber,
            site_project_id=body.ProjectID,
            source_site_name=source_site_name,
        )
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        if project is None:
            project = Project(
                aime_allocation_id=body.GrantNumber,
                name=body.ProjectID or body.GrantNumber,
                grant_number=body.GrantNumber,
                site_project_id=body.ProjectID,
                project_title=body.ProjectID,
                source_site_name=source_site_name,
                allocated_resource=body.AllocatedResource,
                service_units_allocated=self._to_decimal(body.ServiceUnitsAllocated),
                service_units_remaining=self._to_decimal(body.ServiceUnitsRemaining),
                resource_type=resource,
                cpu_allocated=0,
                gpu_allocated=0,
                is_active=True,
            )
            db.add(project)
            db.flush()
            logger.info(
                "Created placeholder project from account packet for grant %s",
                body.GrantNumber,
            )
            return project

        project.grant_number = body.GrantNumber or project.grant_number
        project.site_project_id = body.ProjectID or project.site_project_id
        project.source_site_name = self._preserve_or_set_source_site_name(
            project.source_site_name,
            source_site_name,
        )
        project.allocated_resource = body.AllocatedResource or project.allocated_resource
        new_service_units = self._to_decimal(body.ServiceUnitsAllocated)
        if new_service_units is not None:
            project.service_units_allocated = new_service_units
        new_service_units_remaining = self._to_decimal(body.ServiceUnitsRemaining)
        if new_service_units_remaining is not None:
            project.service_units_remaining = new_service_units_remaining
        project.resource_type = resource or project.resource_type
        if not project.project_title:
            project.project_title = body.ProjectID
        if not project.name:
            project.name = body.ProjectID or body.GrantNumber
        project.is_active = True
        return project

    def _mark_project_received_for_provisioning(
        self,
        db: Session,
        *,
        project: Project,
        packet_type: str,
    ) -> bool:
        """Mark project pending provisioning and alert admins."""
        return self.project_provisioning.mark_received(
            db,
            project=project,
            reason=f"packet:{packet_type}",
        )

    def _assign_user_to_project(
        self,
        db: Session,
        project: Project,
        user: User,
        role: str | None = None,
        resource: str | None = None,
        allocated_resource: str | None = None,
        service_units_allocated: Decimal | None = None,
        service_units_remaining: Decimal | None = None,
        remote_site_login: str | None = None,
        is_active: bool = True,
        account_state: str | None = None,
        source_packet_rec_id: int | None = None,
        source_trans_rec_id: int | None = None,
        source_transaction_id: int | None = None,
    ) -> ProjectUser:
        """Assign a user to a project if not already assigned."""
        now = datetime.now(UTC)
        state_value = account_state or ProjectUser.ACCOUNT_STATE_RECEIVED
        state_rank = ProjectUser.ACCOUNT_STATE_RANK
        existing = (
            db.query(ProjectUser)
            .filter(
                ProjectUser.project_id == project.id,
                ProjectUser.user_id == user.id,
                ProjectUser.resource == resource,
            )
            .first()
        )
        if existing is None:
            pu = ProjectUser(
                project_id=project.id,
                user_id=user.id,
                role=role,
                resource=resource,
                allocated_resource=allocated_resource,
                service_units_allocated=service_units_allocated,
                service_units_remaining=service_units_remaining,
                remote_site_login=remote_site_login,
                is_active=is_active,
                account_state=state_value,
                source_packet_rec_id=source_packet_rec_id,
                source_trans_rec_id=source_trans_rec_id,
                source_transaction_id=source_transaction_id,
                account_state_updated_at=now,
                email_sent_at=(
                    now
                    if state_value == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT
                    else None
                ),
                account_made_at=(
                    now
                    if state_value in (
                        ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
                        ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
                        ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT,
                    )
                    else None
                ),
            )
            db.add(pu)
            db.flush()
            logger.info("Assigned user %s to project %s", user.email, project.name)
            return pu

        existing.role = role or existing.role
        existing.allocated_resource = allocated_resource or existing.allocated_resource
        if service_units_allocated is not None:
            existing.service_units_allocated = service_units_allocated
        if service_units_remaining is not None:
            existing.service_units_remaining = service_units_remaining
        existing.remote_site_login = remote_site_login or existing.remote_site_login
        existing.is_active = is_active
        if account_state is not None and existing.account_state != account_state:
            current_rank = state_rank.get(existing.account_state, 0)
            desired_rank = state_rank.get(account_state, 0)
            if desired_rank >= current_rank:
                existing.account_state = account_state
                existing.account_state_updated_at = now
                if account_state == ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT:
                    existing.email_sent_at = now
                if account_state in (
                    ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
                    ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
                    ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT,
                ):
                    existing.account_made_at = existing.account_made_at or now
        if source_packet_rec_id is not None:
            existing.source_packet_rec_id = source_packet_rec_id
        if source_trans_rec_id is not None:
            existing.source_trans_rec_id = source_trans_rec_id
        if source_transaction_id is not None:
            existing.source_transaction_id = source_transaction_id
        db.flush()
        return existing

    def _record_packet(
        self,
        db: Session,
        *,
        packet_type: str,
        header: dict[str, Any],
        raw_packet: dict[str, Any],
        ingest_source: str = AMIEPacket.INGEST_SOURCE_WORKER,
    ) -> tuple[AMIEPacket, bool]:
        packet_rec_id = int(header["packet_rec_id"])
        existing = db.query(AMIEPacket).filter(AMIEPacket.packet_rec_id == packet_rec_id).first()
        if existing is not None:
            existing.packet_type = packet_type
            existing.trans_rec_id = header.get("trans_rec_id")
            existing.packet_id = header.get("packet_id")
            existing.transaction_id = header.get("transaction_id")
            existing.local_site_name = header.get("local_site_name")
            existing.remote_site_name = header.get("remote_site_name")
            existing.originating_site_name = header.get("originating_site_name")
            existing.outgoing_flag = header.get("outgoing_flag")
            existing.transaction_state = header.get("transaction_state")
            existing.packet_state = header.get("packet_state")
            existing.client_state = header.get("client_state")
            existing.packet_timestamp = header.get("packet_timestamp")
            existing.raw_packet = self._json_compatible(raw_packet)
            existing.ingest_source = ingest_source
            existing.processing_status = AMIEPacket.PROCESSING_STATUS_RECEIVED
            existing.processing_error = None
            existing.processed_at = None
            db.flush()
            return existing, False

        packet = AMIEPacket(
            packet_rec_id=packet_rec_id,
            trans_rec_id=header.get("trans_rec_id"),
            packet_id=header.get("packet_id"),
            transaction_id=header.get("transaction_id"),
            packet_type=packet_type,
            local_site_name=header.get("local_site_name"),
            remote_site_name=header.get("remote_site_name"),
            originating_site_name=header.get("originating_site_name"),
            outgoing_flag=header.get("outgoing_flag"),
            transaction_state=header.get("transaction_state"),
            packet_state=header.get("packet_state"),
            client_state=header.get("client_state"),
            packet_timestamp=header.get("packet_timestamp"),
            processing_status=AMIEPacket.PROCESSING_STATUS_RECEIVED,
            ingest_source=ingest_source,
            raw_packet=self._json_compatible(raw_packet),
        )
        db.add(packet)
        db.flush()
        return packet, True

    def _record_allocation_packet(
        self, db: Session, packet_id: Any, body: RequestProjectCreateBodyBinding
    ) -> None:
        db.add(
            AMIEAllocationPacket(
                packet_id=packet_id,
                grant_number=body.GrantNumber,
                record_id=str(body.RecordID) if body.RecordID is not None else None,
                project_id=body.ProjectID,
                resource=body.ResourceList[0] if body.ResourceList else None,
                allocated_resource=body.AllocatedResource,
                allocation_type=body.AllocationType,
                request_type=body.RequestType,
                service_units_allocated=str(body.ServiceUnitsAllocated),
                service_units_remaining=(
                    str(body.ServiceUnitsRemaining)
                    if body.ServiceUnitsRemaining is not None
                    else None
                ),
                start_date=self._to_date(body.StartDate),
                end_date=self._to_date(body.EndDate),
                project_title=body.ProjectTitle,
                abstract=body.Abstract,
                board_type=body.BoardType,
                charge_number=body.ChargeNumber,
                pfos_number=body.PfosNumber,
                proposal_number=body.ProposalNumber,
                pi_person_id=body.PiPersonID,
                pi_global_id=body.PiGlobalID,
                pi_first_name=body.PiFirstName,
                pi_middle_name=body.PiMiddleName,
                pi_last_name=body.PiLastName,
                pi_email=body.PiEmail,
                pi_title=body.PiTitle,
                pi_organization=body.PiOrganization,
                pi_org_code=body.PiOrgCode,
                sfos=body.Sfos,
                academic_degree=body.AcademicDegree,
                role_list=body.RoleList,
                pi_dn_list=body.PiDnList,
                pi_requested_login_list=body.PiRequestedLoginList,
                site_person_ids=body.SitePersonId,
                raw_body=body.model_dump(mode="json"),
            )
        )

    def _record_new_user_packet(
        self, db: Session, packet_id: Any, body: RequestAccountCreateBodyBinding
    ) -> None:
        db.add(
            AMIENewUserPacket(
                packet_id=packet_id,
                grant_number=body.GrantNumber,
                project_id=body.ProjectID,
                resource=body.ResourceList[0] if body.ResourceList else None,
                allocated_resource=body.AllocatedResource,
                service_units_allocated=(
                    str(body.ServiceUnitsAllocated)
                    if body.ServiceUnitsAllocated is not None
                    else None
                ),
                service_units_remaining=(
                    str(body.ServiceUnitsRemaining)
                    if body.ServiceUnitsRemaining is not None
                    else None
                ),
                user_person_id=body.UserPersonID,
                user_global_id=body.UserGlobalID,
                user_first_name=body.UserFirstName,
                user_middle_name=body.UserMiddleName,
                user_last_name=body.UserLastName,
                user_organization=body.UserOrganization,
                user_org_code=body.UserOrgCode,
                user_title=body.UserTitle,
                user_department=body.UserDepartment,
                user_city=body.UserCity,
                user_state=body.UserState,
                user_country=body.UserCountry,
                user_street_address=body.UserStreetAddress,
                user_street_address2=body.UserStreetAddress2,
                user_zip=body.UserZip,
                user_email=body.UserEmail,
                user_business_phone_number=body.UserBusinessPhoneNumber,
                user_remote_site_login=body.UserRemoteSiteLogin,
                user_password_access_enable=(
                    str(body.UserPasswordAccessEnable)
                    if body.UserPasswordAccessEnable is not None
                    else None
                ),
                nsf_status_code=body.NsfStatusCode,
                role_list=body.RoleList,
                user_dn_list=body.UserDnList,
                user_requested_login_list=body.UserRequestedLoginList,
                site_person_ids=body.SitePersonId,
                raw_body=body.model_dump(mode="json"),
            )
        )

    def _record_lifecycle_packet(
        self,
        db: Session,
        *,
        packet_id: Any,
        packet_type: str,
        raw_body: dict[str, Any],
        project_id: str | None = None,
        grant_number: str | None = None,
        person_id: str | None = None,
        keep_person_id: str | None = None,
        delete_person_id: str | None = None,
        action_type: str | None = None,
        resource: str | None = None,
        allocated_resource: str | None = None,
        service_units_allocated: str | None = None,
        service_units_remaining: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        dn_list: list[str] | None = None,
        status_code: str | None = None,
        detail_code: str | None = None,
        message: str | None = None,
    ) -> None:
        existing = (
            db.query(AMIELifecyclePacket)
            .filter(AMIELifecyclePacket.packet_id == packet_id)
            .first()
        )
        if existing is not None:
            return

        db.add(
            AMIELifecyclePacket(
                packet_id=packet_id,
                packet_type=packet_type,
                project_id=project_id,
                grant_number=grant_number,
                person_id=person_id,
                keep_person_id=keep_person_id,
                delete_person_id=delete_person_id,
                action_type=action_type,
                resource=resource,
                allocated_resource=allocated_resource,
                service_units_allocated=service_units_allocated,
                service_units_remaining=service_units_remaining,
                start_date=start_date,
                end_date=end_date,
                dn_list=dn_list,
                status_code=status_code,
                detail_code=detail_code,
                message=message,
                raw_body=self._json_compatible(raw_body),
            )
        )

    def _handle_data_project_create(
        self,
        db: Session,
        packet: DataProjectCreatePacketBinding,
        packet_record: AMIEPacket,
    ) -> Project | None:
        source_site_name = self._packet_site_name(packet_record)
        project = self._resolve_project(
            db,
            site_project_id=packet.body.ProjectID,
            source_site_name=source_site_name,
        )
        user = self._get_or_create_user_by_person_id(
            db,
            person_id=packet.body.PersonID,
            global_id=packet.body.GlobalID,
            source_site_name=source_site_name,
        )

        user.dn_list = self._merge_dn_list(user.dn_list, packet.body.DnList)
        user.source_site_name = self._preserve_or_set_source_site_name(
            user.source_site_name,
            source_site_name,
        )
        user.is_active = True

        if project is not None:
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            project.is_active = True
            project_users = (
                db.query(ProjectUser)
                .filter(
                    ProjectUser.project_id == project.id,
                    ProjectUser.user_id == user.id,
                )
                .all()
            )
            for pu in project_users:
                pu.is_active = True
                pu.set_account_state(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
                if pu.account_made_at is None:
                    pu.account_made_at = datetime.now(UTC)
                result = self.authentik_service.ensure_user_in_project(
                    user=user,
                    project=project,
                    project_user=pu,
                )
                if not result.get("ok", False):
                    logger.warning(
                        "Failed to ensure PI Authentik membership project=%s user=%s reason=%s",
                        project.site_project_id or project.id,
                        user.person_id or user.email or user.id,
                        result.get("reason") or result.get("status") or "unknown",
                    )
                namespace_result = self.kubernetes_service.ensure_user_project_access(
                    project=project,
                    user=user,
                    project_user=pu,
                )
                if not namespace_result.get("ok", False):
                    logger.warning(
                        "Failed to ensure portal namespace membership project=%s user=%s reason=%s",
                        project.site_project_id or project.id,
                        user.person_id or user.email or user.id,
                        namespace_result.get("reason")
                        or namespace_result.get("status")
                        or "unknown",
                    )

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=packet.body.ProjectID,
            person_id=packet.body.PersonID,
            dn_list=packet.body.DnList,
            raw_body=packet.body.model_dump(mode="json", by_alias=True),
        )
        return project

    def _handle_data_account_create(
        self,
        db: Session,
        packet: DataAccountCreatePacketBinding,
        packet_record: AMIEPacket,
    ) -> Project | None:
        source_site_name = self._packet_site_name(packet_record)
        project = self._resolve_project(
            db,
            site_project_id=packet.body.ProjectID,
            source_site_name=source_site_name,
        )
        user = self._get_or_create_user_by_person_id(
            db,
            person_id=packet.body.PersonID,
            global_id=packet.body.GlobalID,
            source_site_name=source_site_name,
        )

        user.dn_list = self._merge_dn_list(user.dn_list, packet.body.DnList)
        user.source_site_name = self._preserve_or_set_source_site_name(
            user.source_site_name,
            source_site_name,
        )
        user.is_active = True

        if project is not None:
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            project.is_active = True
            project_users = (
                db.query(ProjectUser)
                .filter(
                    ProjectUser.project_id == project.id,
                    ProjectUser.user_id == user.id,
                )
                .all()
            )
            if project_users:
                for pu in project_users:
                    pu.is_active = True
                    pu.set_account_state(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
                    if pu.account_made_at is None:
                        pu.account_made_at = datetime.now(UTC)
                    result = self.authentik_service.ensure_user_in_project(
                        user=user,
                        project=project,
                        project_user=pu,
                    )
                    if not result.get("ok", False):
                        logger.warning(
                            "Failed to ensure user Authentik membership project=%s user=%s reason=%s",
                            project.site_project_id or project.id,
                            user.person_id or user.email or user.id,
                            result.get("reason") or result.get("status") or "unknown",
                        )
                    namespace_result = self.kubernetes_service.ensure_user_project_access(
                        project=project,
                        user=user,
                        project_user=pu,
                    )
                    if not namespace_result.get("ok", False):
                        logger.warning(
                            "Failed to ensure portal namespace membership project=%s user=%s reason=%s",
                            project.site_project_id or project.id,
                            user.person_id or user.email or user.id,
                            namespace_result.get("reason")
                            or namespace_result.get("status")
                            or "unknown",
                        )
            else:
                self._assign_user_to_project(
                    db,
                    project,
                    user,
                    is_active=True,
                    account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
                )
                project_users = (
                    db.query(ProjectUser)
                    .filter(
                        ProjectUser.project_id == project.id,
                        ProjectUser.user_id == user.id,
                    )
                    .all()
                )
                for pu in project_users:
                    result = self.authentik_service.ensure_user_in_project(
                        user=user,
                        project=project,
                        project_user=pu,
                    )
                    if not result.get("ok", False):
                        logger.warning(
                            "Failed to ensure user Authentik membership project=%s user=%s reason=%s",
                            project.site_project_id or project.id,
                            user.person_id or user.email or user.id,
                            result.get("reason") or result.get("status") or "unknown",
                        )
                    namespace_result = self.kubernetes_service.ensure_user_project_access(
                        project=project,
                        user=user,
                        project_user=pu,
                    )
                    if not namespace_result.get("ok", False):
                        logger.warning(
                            "Failed to ensure portal namespace membership project=%s user=%s reason=%s",
                            project.site_project_id or project.id,
                            user.person_id or user.email or user.id,
                            namespace_result.get("reason")
                            or namespace_result.get("status")
                            or "unknown",
                        )

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=packet.body.ProjectID,
            person_id=packet.body.PersonID,
            dn_list=packet.body.DnList,
            raw_body=packet.body.model_dump(mode="json", by_alias=True),
        )
        return project

    def _handle_request_user_modify(
        self,
        db: Session,
        packet: RequestUserModifyPacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        user = self._resolve_user(
            db,
            person_id=body.PersonID,
            source_site_name=source_site_name,
        )
        if user is None:
            user = self._get_or_create_user_by_person_id(
                db,
                person_id=body.PersonID,
                default_name=self._full_name(body.FirstName, body.MiddleName, body.LastName)
                or body.PersonID,
                source_site_name=source_site_name,
            )

        full_name = self._full_name(body.FirstName, body.MiddleName, body.LastName)
        user.name = full_name or user.name
        user.first_name = body.FirstName or user.first_name
        user.middle_name = body.MiddleName or user.middle_name
        user.last_name = body.LastName or user.last_name
        user.organization = body.Organization or user.organization
        user.org_code = body.OrgCode or user.org_code
        user.department = body.Department or user.department
        user.email = body.Email or user.email
        user.nsf_status_code = body.NsfStatusCode or user.nsf_status_code
        user.source_site_name = self._preserve_or_set_source_site_name(
            user.source_site_name,
            source_site_name,
        )

        if body.ActionType == "add":
            user.dn_list = self._merge_dn_list(user.dn_list, body.DnList)
            user.is_active = True
        elif body.ActionType == "replace":
            user.dn_list = self._merge_dn_list([], body.DnList)
            user.is_active = True
        else:
            user.dn_list = self._remove_dn_list(user.dn_list, body.DnList)
            self._refresh_user_active_from_accounts(db, user)

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            person_id=body.PersonID,
            action_type=body.ActionType,
            dn_list=body.DnList,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _merge_users(self, db: Session, *, keep: User, delete: User) -> None:
        keep.dn_list = self._merge_dn_list(keep.dn_list, delete.dn_list)

        attrs = [
            "name",
            "first_name",
            "middle_name",
            "last_name",
            "email",
            "global_id",
            "organization",
            "org_code",
            "department",
            "nsf_status_code",
            "remote_site_login",
        ]
        for attr in attrs:
            keep_value = getattr(keep, attr)
            delete_value = getattr(delete, attr)
            if (keep_value is None or keep_value == "") and delete_value not in (None, ""):
                setattr(keep, attr, delete_value)

        for pu in list(delete.project_users):
            existing = (
                db.query(ProjectUser)
                .filter(
                    ProjectUser.project_id == pu.project_id,
                    ProjectUser.user_id == keep.id,
                    ProjectUser.resource == pu.resource,
                )
                .first()
            )
            if existing is None:
                pu.user_id = keep.id
            else:
                existing.role = existing.role or pu.role
                existing.allocated_resource = (
                    existing.allocated_resource or pu.allocated_resource
                )
                if existing.service_units_allocated is None:
                    existing.service_units_allocated = pu.service_units_allocated
                if existing.service_units_remaining is None:
                    existing.service_units_remaining = pu.service_units_remaining
                existing.remote_site_login = (
                    existing.remote_site_login or pu.remote_site_login
                )
                existing.is_active = existing.is_active or pu.is_active
                db.delete(pu)

        keep.is_active = keep.is_active or delete.is_active
        db.delete(delete)

    def _handle_request_person_merge(
        self,
        db: Session,
        packet: RequestPersonMergePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        keep_user = self._resolve_user(
            db,
            person_id=body.KeepPersonID,
            global_id=body.KeepGlobalID,
            source_site_name=source_site_name,
        )
        delete_user = self._resolve_user(
            db,
            person_id=body.DeletePersonID,
            global_id=body.DeleteGlobalID,
            source_site_name=source_site_name,
        )

        if keep_user is None and delete_user is None:
            keep_user = self._get_or_create_user_by_person_id(
                db,
                person_id=body.KeepPersonID,
                default_name=body.KeepPersonID,
                global_id=body.KeepGlobalID,
                source_site_name=source_site_name,
            )
        elif keep_user is None and delete_user is not None:
            keep_user = delete_user

        if keep_user is None:
            return

        keep_user.person_id = body.KeepPersonID
        if body.KeepGlobalID:
            keep_user.global_id = body.KeepGlobalID
        keep_user.source_site_name = self._preserve_or_set_source_site_name(
            keep_user.source_site_name,
            source_site_name,
        )

        if delete_user is not None and delete_user.id != keep_user.id:
            self._merge_users(db, keep=keep_user, delete=delete_user)

        keep_user.is_active = True

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            keep_person_id=body.KeepPersonID,
            delete_person_id=body.DeletePersonID,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _handle_request_project_inactivate(
        self,
        db: Session,
        packet: RequestProjectInactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> Project | None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        project = self._resolve_project(
            db,
            site_project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            source_site_name=source_site_name,
        )

        if project is not None:
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            project.allocated_resource = body.AllocatedResource or project.allocated_resource
            new_su_allocated = self._to_decimal(body.ServiceUnitsAllocated)
            if new_su_allocated is not None:
                project.service_units_allocated = new_su_allocated
            new_su_remaining = self._to_decimal(body.ServiceUnitsRemaining)
            if new_su_remaining is not None:
                project.service_units_remaining = new_su_remaining
            project.is_active = False
            # Project inactivation should only affect project-level scheduling
            # priority, not account usability.
            # Users and project-user links remain active so they can still
            # log in and submit jobs.

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            service_units_allocated=(
                str(body.ServiceUnitsAllocated)
                if body.ServiceUnitsAllocated is not None
                else None
            ),
            service_units_remaining=(
                str(body.ServiceUnitsRemaining)
                if body.ServiceUnitsRemaining is not None
                else None
            ),
            start_date=self._to_date(body.StartDate),
            end_date=self._to_date(body.EndDate),
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )
        return project

    def _handle_request_project_reactivate(
        self,
        db: Session,
        packet: RequestProjectReactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> Project | None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        project = self._resolve_project(
            db,
            site_project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            source_site_name=source_site_name,
        )
        if project is not None:
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            project.allocated_resource = body.AllocatedResource or project.allocated_resource
            new_su_allocated = self._to_decimal(body.ServiceUnitsAllocated)
            if new_su_allocated is not None:
                project.service_units_allocated = new_su_allocated
            new_su_remaining = self._to_decimal(body.ServiceUnitsRemaining)
            if new_su_remaining is not None:
                project.service_units_remaining = new_su_remaining
            project.is_active = True
            project_users = (
                db.query(ProjectUser)
                .filter(
                    ProjectUser.project_id == project.id,
                    or_(ProjectUser.resource == resource, ProjectUser.resource.is_(None)),
                )
                .all()
            )
            users_seen: set[Any] = set()
            for pu in project_users:
                pu.allocated_resource = body.AllocatedResource or pu.allocated_resource
                new_su_allocated = self._to_decimal(body.ServiceUnitsAllocated)
                if new_su_allocated is not None:
                    pu.service_units_allocated = new_su_allocated
                new_su_remaining = self._to_decimal(body.ServiceUnitsRemaining)
                if new_su_remaining is not None:
                    pu.service_units_remaining = new_su_remaining
                pu.is_active = True
                if pu.user_id:
                    users_seen.add(pu.user_id)
            if users_seen:
                users = db.query(User).filter(User.id.in_(users_seen)).all()
                for existing_user in users:
                    self._refresh_user_active_from_accounts(db, existing_user)

        if project is not None and body.PersonID:
            user = self._get_or_create_user_by_person_id(
                db,
                person_id=body.PersonID,
                default_name=body.PersonID,
                source_site_name=source_site_name,
            )
            self._assign_user_to_project(
                db,
                project,
                user,
                role="pi",
                resource=resource,
                allocated_resource=body.AllocatedResource,
                service_units_allocated=self._to_decimal(body.ServiceUnitsAllocated),
                service_units_remaining=self._to_decimal(body.ServiceUnitsRemaining),
                is_active=True,
                account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            )
            user.is_active = True

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            service_units_allocated=(
                str(body.ServiceUnitsAllocated)
                if body.ServiceUnitsAllocated is not None
                else None
            ),
            service_units_remaining=(
                str(body.ServiceUnitsRemaining)
                if body.ServiceUnitsRemaining is not None
                else None
            ),
            start_date=self._to_date(body.StartDate),
            end_date=self._to_date(body.EndDate),
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )
        return project

    def _handle_request_account_inactivate(
        self,
        db: Session,
        packet: RequestAccountInactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> Project | None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        project = self._resolve_project(
            db,
            site_project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            source_site_name=source_site_name,
        )
        user = self._resolve_user(
            db,
            person_id=body.PersonID,
            source_site_name=source_site_name,
        )

        if project is not None and user is not None:
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            user.source_site_name = self._preserve_or_set_source_site_name(
                user.source_site_name,
                source_site_name,
            )
            project_users = (
                db.query(ProjectUser)
                .filter(
                    ProjectUser.project_id == project.id,
                    ProjectUser.user_id == user.id,
                    or_(ProjectUser.resource == resource, ProjectUser.resource.is_(None)),
                )
                .all()
            )
            for pu in project_users:
                pu.allocated_resource = body.AllocatedResource or pu.allocated_resource
                pu.is_active = False
                result = self.authentik_service.remove_user_from_project(
                    user=user,
                    project=project,
                    project_user=pu,
                )
                if not result.get("ok", False):
                    logger.warning(
                        "Failed to remove user from Authentik membership project=%s user=%s reason=%s",
                        project.site_project_id or project.id,
                        user.person_id or user.email or user.id,
                        result.get("reason") or result.get("status") or "unknown",
                    )
                namespace_result = self.kubernetes_service.remove_user_project_access(
                    project=project,
                    user=user,
                    project_user=pu,
                )
                if not namespace_result.get("ok", False):
                    logger.warning(
                        "Failed to remove portal namespace membership project=%s user=%s reason=%s",
                        project.site_project_id or project.id,
                        user.person_id or user.email or user.id,
                        namespace_result.get("reason")
                        or namespace_result.get("status")
                        or "unknown",
                    )
            self._refresh_user_active_from_accounts(db, user)

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID or (project.site_project_id if project else None),
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )
        return project

    def _handle_request_account_reactivate(
        self,
        db: Session,
        packet: RequestAccountReactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> Project | None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        project = self._resolve_project(
            db,
            site_project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            source_site_name=source_site_name,
        )
        user = self._get_or_create_user_by_person_id(
            db,
            person_id=body.PersonID,
            default_name=body.PersonID,
            source_site_name=source_site_name,
        )

        if project is not None:
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            project.is_active = True
            self._assign_user_to_project(
                db,
                project,
                user,
                resource=resource,
                allocated_resource=body.AllocatedResource,
                is_active=True,
                account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            )
            project_users = (
                db.query(ProjectUser)
                .filter(
                    ProjectUser.project_id == project.id,
                    ProjectUser.user_id == user.id,
                    or_(ProjectUser.resource == resource, ProjectUser.resource.is_(None)),
                )
                .all()
            )
            for pu in project_users:
                pu.allocated_resource = body.AllocatedResource or pu.allocated_resource
                result = self.authentik_service.ensure_user_in_project(
                    user=user,
                    project=project,
                    project_user=pu,
                )
                if not result.get("ok", False):
                    logger.warning(
                        "Failed to ensure user Authentik membership project=%s user=%s reason=%s",
                        project.site_project_id or project.id,
                        user.person_id or user.email or user.id,
                        result.get("reason") or result.get("status") or "unknown",
                    )
                namespace_result = self.kubernetes_service.ensure_user_project_access(
                    project=project,
                    user=user,
                    project_user=pu,
                )
                if not namespace_result.get("ok", False):
                    logger.warning(
                        "Failed to ensure portal namespace membership project=%s user=%s reason=%s",
                        project.site_project_id or project.id,
                        user.person_id or user.email or user.id,
                        namespace_result.get("reason")
                        or namespace_result.get("status")
                        or "unknown",
                    )
        user.source_site_name = self._preserve_or_set_source_site_name(
            user.source_site_name,
            source_site_name,
        )
        user.is_active = True

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID or (project.site_project_id if project else None),
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )
        return project

    def _handle_notify_project_create(
        self,
        db: Session,
        packet: NotifyProjectCreatePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        allocation_record_id = (
            str(body.RecordID).strip() if body.RecordID is not None else None
        ) or None
        project = self._resolve_project(
            db,
            grant_number=body.GrantNumber,
            site_project_id=body.ProjectID,
            allocation_record_id=allocation_record_id,
            source_site_name=source_site_name,
        )
        if project is None:
            project = Project(
                aime_allocation_id=allocation_record_id or body.GrantNumber,
                name=body.ProjectTitle or body.ProjectID or body.GrantNumber,
                grant_number=body.GrantNumber,
                allocation_record_id=allocation_record_id,
                site_project_id=body.ProjectID,
                allocation_type=body.AllocationType,
                request_type=body.RequestType,
                source_site_name=source_site_name,
                allocated_resource=body.AllocatedResource,
                service_units_allocated=self._to_decimal(body.ServiceUnitsAllocated),
                service_units_remaining=self._to_decimal(body.ServiceUnitsRemaining),
                start_date=self._to_date(body.StartDate),
                end_date=self._to_date(body.EndDate),
                project_title=body.ProjectTitle,
                pfos_number=body.PfosNumber,
                pi_person_id=body.PiPersonID,
                pi_first_name=body.PiFirstName,
                pi_middle_name=body.PiMiddleName,
                pi_last_name=body.PiLastName,
                pi_email=body.PiEmail,
                pi_organization=body.PiOrganization,
                pi_org_code=body.PiOrgCode,
                pi_department=body.PiDepartment,
                pi_business_phone_number=body.PiBusinessPhoneNumber,
                resource_type=resource,
                cpu_allocated=0,
                gpu_allocated=0,
                is_active=True,
            )
            db.add(project)
            db.flush()
        else:
            project.grant_number = body.GrantNumber or project.grant_number
            project.site_project_id = body.ProjectID or project.site_project_id
            project.allocation_record_id = allocation_record_id or project.allocation_record_id
            project.allocation_type = body.AllocationType or project.allocation_type
            project.request_type = body.RequestType or project.request_type
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            project.name = body.ProjectTitle or project.name
            project.allocated_resource = body.AllocatedResource or project.allocated_resource
            new_su_allocated = self._to_decimal(body.ServiceUnitsAllocated)
            if new_su_allocated is not None:
                project.service_units_allocated = new_su_allocated
            new_su_remaining = self._to_decimal(body.ServiceUnitsRemaining)
            if new_su_remaining is not None:
                project.service_units_remaining = new_su_remaining
            project.start_date = self._to_date(body.StartDate) or project.start_date
            project.end_date = self._to_date(body.EndDate) or project.end_date
            project.project_title = body.ProjectTitle or project.project_title
            project.pfos_number = body.PfosNumber or project.pfos_number
            project.pi_person_id = body.PiPersonID or project.pi_person_id
            project.pi_first_name = body.PiFirstName or project.pi_first_name
            project.pi_middle_name = body.PiMiddleName or project.pi_middle_name
            project.pi_last_name = body.PiLastName or project.pi_last_name
            project.pi_email = body.PiEmail or project.pi_email
            project.pi_organization = body.PiOrganization or project.pi_organization
            project.pi_org_code = body.PiOrgCode or project.pi_org_code
            project.pi_department = body.PiDepartment or project.pi_department
            project.pi_business_phone_number = (
                body.PiBusinessPhoneNumber or project.pi_business_phone_number
            )
            project.resource_type = resource or project.resource_type
            project.is_active = True

        if body.PiPersonID:
            pi_name = self._full_name(body.PiFirstName, body.PiMiddleName, body.PiLastName)
            pi_user = self._get_or_create_user_by_person_id(
                db,
                person_id=body.PiPersonID,
                default_name=pi_name or body.PiPersonID,
                global_id=body.PiGlobalID,
                source_site_name=source_site_name,
            )
            pi_user.name = pi_name or pi_user.name
            pi_user.first_name = body.PiFirstName or pi_user.first_name
            pi_user.middle_name = body.PiMiddleName or pi_user.middle_name
            pi_user.last_name = body.PiLastName or pi_user.last_name
            pi_user.email = body.PiEmail or pi_user.email
            pi_user.organization = body.PiOrganization or pi_user.organization
            pi_user.org_code = body.PiOrgCode or pi_user.org_code
            pi_user.department = body.PiDepartment or pi_user.department
            pi_user.dn_list = self._merge_dn_list(pi_user.dn_list, body.PiDnList)
            if body.PiRemoteSiteLogin:
                pi_user.remote_site_login = body.PiRemoteSiteLogin
            pi_user.source_site_name = self._preserve_or_set_source_site_name(
                pi_user.source_site_name,
                source_site_name,
            )
            if (
                pi_user.service_units_allocated is None
                and project.service_units_allocated is not None
            ):
                pi_user.service_units_allocated = project.service_units_allocated
            pi_user.is_active = True
            self._assign_user_to_project(
                db,
                project,
                pi_user,
                role="pi",
                resource=resource,
                allocated_resource=body.AllocatedResource,
                service_units_allocated=self._to_decimal(body.ServiceUnitsAllocated),
                service_units_remaining=self._to_decimal(body.ServiceUnitsRemaining),
                remote_site_login=body.PiRemoteSiteLogin,
                is_active=True,
                account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            )

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.PiPersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            service_units_allocated=(
                str(body.ServiceUnitsAllocated)
                if body.ServiceUnitsAllocated is not None
                else None
            ),
            service_units_remaining=(
                str(body.ServiceUnitsRemaining)
                if body.ServiceUnitsRemaining is not None
                else None
            ),
            start_date=self._to_date(body.StartDate),
            end_date=self._to_date(body.EndDate),
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _handle_notify_account_create(
        self,
        db: Session,
        packet: NotifyAccountCreatePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        source_site_name = self._packet_site_name(packet_record)
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        project = self._resolve_project(
            db,
            site_project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            source_site_name=source_site_name,
        )
        if project is not None:
            project.source_site_name = self._preserve_or_set_source_site_name(
                project.source_site_name,
                source_site_name,
            )
            project.allocated_resource = body.AllocatedResource or project.allocated_resource
            new_su_allocated = self._to_decimal(body.ServiceUnitsAllocated)
            if new_su_allocated is not None:
                project.service_units_allocated = new_su_allocated
            new_su_remaining = self._to_decimal(body.ServiceUnitsRemaining)
            if new_su_remaining is not None:
                project.service_units_remaining = new_su_remaining
            project.resource_type = resource or project.resource_type
            project.is_active = True

        full_name = self._full_name(body.UserFirstName, body.UserMiddleName, body.UserLastName)
        user = self._resolve_user(
            db,
            person_id=body.UserPersonID,
            email=body.UserEmail,
            global_id=body.UserGlobalID,
            source_site_name=source_site_name,
        )
        if user is None and body.UserPersonID:
            user = self._get_or_create_user_by_person_id(
                db,
                person_id=body.UserPersonID,
                default_name=full_name or body.UserPersonID,
                global_id=body.UserGlobalID,
                source_site_name=source_site_name,
            )
        if user is None:
            user = User(
                email=body.UserEmail,
                name=full_name or body.UserOrganization or body.UserGlobalID or "Unknown User",
                first_name=body.UserFirstName,
                middle_name=body.UserMiddleName,
                last_name=body.UserLastName,
                person_id=body.UserPersonID,
                global_id=body.UserGlobalID,
                organization=body.UserOrganization,
                org_code=body.UserOrgCode,
                department=body.UserDepartment,
                nsf_status_code=body.NsfStatusCode,
                source_site_name=source_site_name,
                dn_list=self._merge_dn_list([], body.UserDnList),
                remote_site_login=body.UserRemoteSiteLogin,
                is_active=True,
            )
            db.add(user)
            db.flush()
            logger.info(
                "Created placeholder user from notify_account_create for ProjectID=%s",
                body.ProjectID,
            )

        user.name = full_name or user.name
        user.first_name = body.UserFirstName or user.first_name
        user.middle_name = body.UserMiddleName or user.middle_name
        user.last_name = body.UserLastName or user.last_name
        user.person_id = body.UserPersonID or user.person_id
        user.global_id = body.UserGlobalID or user.global_id
        user.email = body.UserEmail or user.email
        user.organization = body.UserOrganization or user.organization
        user.org_code = body.UserOrgCode or user.org_code
        user.department = body.UserDepartment or user.department
        user.nsf_status_code = body.NsfStatusCode or user.nsf_status_code
        user.dn_list = self._merge_dn_list(user.dn_list, body.UserDnList)
        user.remote_site_login = body.UserRemoteSiteLogin or user.remote_site_login
        user.source_site_name = self._preserve_or_set_source_site_name(
            user.source_site_name,
            source_site_name,
        )
        new_user_su_allocated = self._to_decimal(body.ServiceUnitsAllocated)
        if new_user_su_allocated is not None:
            user.service_units_allocated = new_user_su_allocated
        if user.service_units_allocated is None and project is not None:
            user.service_units_allocated = project.service_units_allocated
        user.is_active = True

        if project is not None:
            role = body.RoleList[0] if body.RoleList else None
            self._assign_user_to_project(
                db,
                project,
                user,
                role=role,
                resource=resource,
                allocated_resource=body.AllocatedResource,
                service_units_allocated=self._to_decimal(body.ServiceUnitsAllocated),
                service_units_remaining=self._to_decimal(body.ServiceUnitsRemaining),
                remote_site_login=body.UserRemoteSiteLogin,
                is_active=True,
                account_state=ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,
            )

        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.UserPersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            service_units_allocated=(
                str(body.ServiceUnitsAllocated)
                if body.ServiceUnitsAllocated is not None
                else None
            ),
            service_units_remaining=(
                str(body.ServiceUnitsRemaining)
                if body.ServiceUnitsRemaining is not None
                else None
            ),
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _handle_notify_project_inactivate(
        self,
        db: Session,
        packet: NotifyProjectInactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            service_units_allocated=(
                str(body.ServiceUnitsAllocated)
                if body.ServiceUnitsAllocated is not None
                else None
            ),
            service_units_remaining=(
                str(body.ServiceUnitsRemaining)
                if body.ServiceUnitsRemaining is not None
                else None
            ),
            start_date=self._to_date(body.StartDate),
            end_date=self._to_date(body.EndDate),
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _handle_notify_project_reactivate(
        self,
        db: Session,
        packet: NotifyProjectReactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            service_units_allocated=(
                str(body.ServiceUnitsAllocated)
                if body.ServiceUnitsAllocated is not None
                else None
            ),
            service_units_remaining=(
                str(body.ServiceUnitsRemaining)
                if body.ServiceUnitsRemaining is not None
                else None
            ),
            start_date=self._to_date(body.StartDate),
            end_date=self._to_date(body.EndDate),
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _handle_notify_account_inactivate(
        self,
        db: Session,
        packet: NotifyAccountInactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _handle_notify_account_reactivate(
        self,
        db: Session,
        packet: NotifyAccountReactivatePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        resource = body.AllocatedResource or (body.ResourceList[0] if body.ResourceList else None)
        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            project_id=body.ProjectID,
            grant_number=body.GrantNumber,
            person_id=body.PersonID,
            resource=resource,
            allocated_resource=body.AllocatedResource,
            message=body.Comment,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    def _handle_inform_transaction_complete(
        self,
        db: Session,
        packet: InformTransactionCompletePacketBinding,
        packet_record: AMIEPacket,
    ) -> None:
        body = packet.body
        self._record_lifecycle_packet(
            db,
            packet_id=packet_record.id,
            packet_type=packet.type,
            status_code=str(body.StatusCode),
            detail_code=str(body.DetailCode),
            message=body.Message,
            raw_body=body.model_dump(mode="json", by_alias=True),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def mark_packet_error(
        self,
        db: Session,
        packet: dict | Any,
        *,
        error_message: str,
        ingest_source: str = AMIEPacket.INGEST_SOURCE_WORKER,
    ) -> None:
        """Persist packet metadata (if needed) and mark processing as failed."""
        packet_dict = coerce_packet_dict(packet)
        packet_type = str(packet_dict.get("type") or "unknown")
        header = packet_dict.get("header", {})
        try:
            packet_record, _ = self._record_packet(
                db,
                packet_type=packet_type,
                header=header,
                raw_packet=packet_dict,
                ingest_source=ingest_source,
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "Unable to persist packet error status type=%s packet_rec_id=%s",
                packet_type,
                header.get("packet_rec_id"),
            )
            return

        packet_record.processing_status = AMIEPacket.PROCESSING_STATUS_ERROR
        packet_record.processing_error = error_message
        packet_record.processed_at = None
        db.commit()

    def validate_packet_dry_run(self, packet: dict | Any) -> dict[str, Any]:
        """Validate packet bindings without ingesting data."""
        packet_dict = coerce_packet_dict(packet)
        packet_type = str(packet_dict.get("type") or "unknown")
        errors: list[dict[str, str]] = []

        try:
            bound_packet = bind_packet(packet_dict)
            return {
                "valid": True,
                "packet_type": packet_type,
                "bound_type": bound_packet.__class__.__name__,
                "errors": [],
                "suggestions": [],
            }
        except UnsupportedPacketType as exc:
            errors.append(
                {
                    "kind": "unsupported_type",
                    "message": str(exc),
                    "suggestion": "Use a supported AMIE packet type or map this type in bindings.py.",
                }
            )
        except ValidationError as exc:
            for item in exc.errors():
                loc = ".".join(str(part) for part in item.get("loc", []))
                msg = str(item.get("msg", "validation error"))
                suggestion = (
                    "Check required fields and value types for this packet binding."
                    if "Field required" in msg
                    else "Match the expected schema for this field."
                )
                errors.append(
                    {
                        "kind": "validation_error",
                        "location": loc,
                        "message": msg,
                        "suggestion": suggestion,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "kind": "validation_exception",
                    "message": str(exc),
                    "suggestion": "Review payload/header shape and field names.",
                }
            )

        return {
            "valid": False,
            "packet_type": packet_type,
            "bound_type": None,
            "errors": errors,
            "suggestions": [item["suggestion"] for item in errors if "suggestion" in item],
        }

    @staticmethod
    def _emit_project_user_packet_alert(
        db: Session,
        *,
        packet_record: AMIEPacket,
        processed_ok: bool,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        """Send alert for new user account request packets."""
        alert_info = ObservabilityService.project_user_packet_alert_fields(packet_record)
        if alert_info is None:
            return
        category, title = alert_info
        severity = "info" if processed_ok else "warn"
        message = (
            "A new user account request has been received and awaits admin action."
            if processed_ok
            else (
                f"User account request packet was received but not fully processed "
                f"(packet_rec_id={packet_record.packet_rec_id}, status={packet_record.processing_status})"
            )
        )
        payload: dict[str, Any] = {}
        if extra_payload:
            payload.update(extra_payload)
        payload.update(
            {
                "packet_rec_id": packet_record.packet_rec_id,
                "processing_status": packet_record.processing_status,
            }
        )
        if packet_record.processing_error:
            payload["processing_error"] = packet_record.processing_error
        AlertService.send(
            db,
            alert_key=f"{category}:{packet_record.packet_rec_id}",
            category=category,
            severity=severity,
            title=title,
            message=message,
            payload=payload,
        )

    def ingest_packet(
        self,
        db: Session,
        packet: dict | Any,
        *,
        ingest_source: str = AMIEPacket.INGEST_SOURCE_WORKER,
    ) -> IngestResult:
        """Process a raw AMIE packet.

        Args:
            db: Active SQLAlchemy session.
            packet: A dictionary or ``amieclient`` packet object.

        Returns:
            :class:`IngestResult` indicating whether packet type is supported,
            and the affected project when available.
        """
        packet_dict = coerce_packet_dict(packet)
        packet_type = str(packet_dict.get("type") or "unknown")
        header = packet_dict.get("header", {})
        logger.debug(
            "AIME ingest_packet received packet type=%s packet_rec_id=%s payload=%s",
            packet_type,
            header.get("packet_rec_id"),
            packet_dict,
        )

        packet_record, created = self._record_packet(
            db,
            packet_type=packet_type,
            header=header,
            raw_packet=packet_dict,
            ingest_source=ingest_source,
        )

        try:
            bound_packet = bind_packet(packet_dict)
        except UnsupportedPacketType as exc:
            logger.info("Skipping unsupported packet payload: %s", exc)
            packet_record.processing_status = AMIEPacket.PROCESSING_STATUS_UNPROCESSED
            packet_record.processing_error = str(exc)
            packet_record.processed_at = None
            db.commit()
            self._emit_project_user_packet_alert(
                db,
                packet_record=packet_record,
                processed_ok=False,
            )
            return IngestResult(handled=False, packet_type=packet_type)
        except ValidationError as exc:
            packet_record.processing_status = AMIEPacket.PROCESSING_STATUS_ERROR
            packet_record.processing_error = f"ValidationError: {exc}"
            packet_record.processed_at = None
            db.commit()
            self._emit_project_user_packet_alert(
                db,
                packet_record=packet_record,
                processed_ok=False,
            )
            return IngestResult(handled=False, packet_type=packet_type)

        packet_record.packet_type = bound_packet.type

        project: Project | None = None
        project_needs_provision_alert = False
        extra_alert_payload: dict[str, Any] | None = None
        source_site_name = self._packet_site_name(packet_record)

        if isinstance(bound_packet, RequestProjectCreatePacketBinding):
            project = self._upsert_project_from_allocation(
                db,
                bound_packet.body,
                source_site_name=source_site_name,
            )
            project_needs_provision_alert = self._mark_project_received_for_provisioning(
                db,
                project=project,
                packet_type=bound_packet.type,
            )
            project.source_packet_rec_id = packet_record.packet_rec_id
            project.source_trans_rec_id = packet_record.trans_rec_id
            project.source_transaction_id = packet_record.transaction_id
            if created:
                self._record_allocation_packet(db, packet_record.id, bound_packet.body)
            pi_user = self._get_or_create_user_from_pi(
                db,
                bound_packet.body,
                source_site_name=source_site_name,
            )
            if (
                pi_user.service_units_allocated is None
                and project.service_units_allocated is not None
            ):
                pi_user.service_units_allocated = project.service_units_allocated
            role = bound_packet.body.RoleList[0] if bound_packet.body.RoleList else "pi"
            resource = (
                bound_packet.body.AllocatedResource
                or (
                    bound_packet.body.ResourceList[0]
                    if bound_packet.body.ResourceList
                    else None
                )
            )
            self._assign_user_to_project(
                db,
                project,
                pi_user,
                role=role,
                resource=resource,
                allocated_resource=bound_packet.body.AllocatedResource,
                service_units_allocated=self._to_decimal(
                    bound_packet.body.ServiceUnitsAllocated
                ),
                service_units_remaining=self._to_decimal(
                    bound_packet.body.ServiceUnitsRemaining
                ),
                is_active=True,
                account_state=ProjectUser.ACCOUNT_STATE_RECEIVED,
                source_packet_rec_id=packet_record.packet_rec_id,
                source_trans_rec_id=packet_record.trans_rec_id,
                source_transaction_id=packet_record.transaction_id,
            )

        elif isinstance(bound_packet, RequestAccountCreatePacketBinding):
            project = self._upsert_project_from_account(
                db,
                bound_packet.body,
                source_site_name=source_site_name,
            )
            project_needs_provision_alert = self._mark_project_received_for_provisioning(
                db,
                project=project,
                packet_type=bound_packet.type,
            )
            project.source_packet_rec_id = packet_record.packet_rec_id
            project.source_trans_rec_id = packet_record.trans_rec_id
            project.source_transaction_id = packet_record.transaction_id
            if created:
                self._record_new_user_packet(db, packet_record.id, bound_packet.body)
            user = self._get_or_create_user_from_account(
                db,
                bound_packet.body,
                source_site_name=source_site_name,
            )
            if (
                user.service_units_allocated is None
                and project.service_units_allocated is not None
            ):
                user.service_units_allocated = project.service_units_allocated
            role = bound_packet.body.RoleList[0] if bound_packet.body.RoleList else None
            resource = (
                bound_packet.body.AllocatedResource
                or (
                    bound_packet.body.ResourceList[0]
                    if bound_packet.body.ResourceList
                    else None
                )
            )
            self._assign_user_to_project(
                db,
                project,
                user,
                role=role,
                resource=resource,
                allocated_resource=bound_packet.body.AllocatedResource,
                service_units_allocated=self._to_decimal(
                    bound_packet.body.ServiceUnitsAllocated
                ),
                service_units_remaining=self._to_decimal(
                    bound_packet.body.ServiceUnitsRemaining
                ),
                remote_site_login=bound_packet.body.UserRemoteSiteLogin,
                is_active=True,
                account_state=ProjectUser.ACCOUNT_STATE_RECEIVED,
                source_packet_rec_id=packet_record.packet_rec_id,
                source_trans_rec_id=packet_record.trans_rec_id,
                source_transaction_id=packet_record.transaction_id,
            )
            body = bound_packet.body
            extra_alert_payload = {
                "name": " ".join(
                    filter(None, [body.UserFirstName, body.UserLastName])
                ),
                "email": body.UserEmail,
                "institution": body.UserOrganization,
                "allocation_id": project.aime_allocation_id,
            }

        elif isinstance(bound_packet, DataProjectCreatePacketBinding):
            project = self._handle_data_project_create(db, bound_packet, packet_record)

        elif isinstance(bound_packet, DataAccountCreatePacketBinding):
            project = self._handle_data_account_create(db, bound_packet, packet_record)

        elif isinstance(bound_packet, NotifyProjectCreatePacketBinding):
            self._handle_notify_project_create(db, bound_packet, packet_record)

        elif isinstance(bound_packet, NotifyAccountCreatePacketBinding):
            self._handle_notify_account_create(db, bound_packet, packet_record)

        elif isinstance(bound_packet, NotifyProjectInactivatePacketBinding):
            self._handle_notify_project_inactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, NotifyProjectReactivatePacketBinding):
            self._handle_notify_project_reactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, NotifyAccountInactivatePacketBinding):
            self._handle_notify_account_inactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, NotifyAccountReactivatePacketBinding):
            self._handle_notify_account_reactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, RequestUserModifyPacketBinding):
            self._handle_request_user_modify(db, bound_packet, packet_record)

        elif isinstance(bound_packet, RequestPersonMergePacketBinding):
            self._handle_request_person_merge(db, bound_packet, packet_record)

        elif isinstance(bound_packet, RequestProjectInactivatePacketBinding):
            project = self._handle_request_project_inactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, RequestProjectReactivatePacketBinding):
            project = self._handle_request_project_reactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, RequestAccountInactivatePacketBinding):
            project = self._handle_request_account_inactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, RequestAccountReactivatePacketBinding):
            project = self._handle_request_account_reactivate(db, bound_packet, packet_record)

        elif isinstance(bound_packet, InformTransactionCompletePacketBinding):
            self._handle_inform_transaction_complete(db, bound_packet, packet_record)

        else:
            logger.info("Bound but unhandled packet type: %s", bound_packet.type)
            packet_record.processing_status = AMIEPacket.PROCESSING_STATUS_UNPROCESSED
            packet_record.processing_error = (
                f"Bound but unhandled packet type: {bound_packet.type}"
            )
            packet_record.processed_at = None
            db.commit()
            self._emit_project_user_packet_alert(
                db,
                packet_record=packet_record,
                processed_ok=False,
            )
            return IngestResult(handled=False, packet_type=bound_packet.type)

        packet_record.processing_status = AMIEPacket.PROCESSING_STATUS_PROCESSED
        packet_record.processing_error = None
        packet_record.processed_at = datetime.now(UTC)
        db.commit()
        if project is not None and project_needs_provision_alert:
            self.project_provisioning.emit_required_alert(
                db,
                project=project,
                reason=f"packet:{bound_packet.type}",
            )
        self._emit_project_user_packet_alert(
            db,
            packet_record=packet_record,
            processed_ok=True,
            extra_payload=extra_alert_payload,
        )
        return IngestResult(handled=True, packet_type=bound_packet.type, project=project)
