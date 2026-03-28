"""Project-user account lifecycle management."""

from __future__ import annotations

from contextlib import ExitStack
import logging
from datetime import UTC, datetime
from typing import Any

from amieclient import AMIEClient
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config import configured_amie_site_names, settings
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.amie_packet import AMIEPacket
from app.models.outbound_packet_log import OutboundPacketLog
from app.models.project import Project
from app.models.project_invite import ProjectInvite
from app.models.project_invite_event import ProjectInviteEvent
from app.models.project_user import ProjectUser
from app.services.outbound_packets import OutboundPacketService

logger = logging.getLogger(__name__)


def _log_amie_interaction(action: str, **context: object) -> None:
    """Emit a consistent INFO log line for AMIE API interactions."""
    details = ", ".join(f"{key}={value!r}" for key, value in sorted(context.items()))
    if details:
        logger.info("AMIE interaction action=%s %s", action, details)
    else:
        logger.info("AMIE interaction action=%s", action)


class AccountLifecycleService:
    """Handle account state transitions and AIME confirmation packets."""

    def __init__(self) -> None:
        """Initialize account lifecycle service."""

    @staticmethod
    def mark_received(
        project_user: ProjectUser,
        *,
        source_packet_rec_id: int | None = None,
    ) -> None:
        """Set state for newly received account requests."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_RECEIVED)
        if source_packet_rec_id is not None:
            project_user.source_packet_rec_id = source_packet_rec_id

    # Legacy alias kept for call-sites that haven't been updated yet.
    mark_just_received = mark_received

    @staticmethod
    def mark_email_sent(project_user: ProjectUser) -> None:
        """Set state when invite email has been sent."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_EMAIL_INVITE_SENT)
        project_user.email_sent_at = datetime.now(UTC)

    @staticmethod
    def mark_user_completed_oauth(project_user: ProjectUser) -> None:
        """Set state when user completed the OAuth onboarding flow."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH)
        if project_user.account_made_at is None:
            project_user.account_made_at = datetime.now(UTC)

    # Legacy alias – callers that used mark_account_made now mean OAuth complete.
    mark_account_made = mark_user_completed_oauth

    @staticmethod
    def mark_aime_notified(project_user: ProjectUser) -> None:
        """Set state when notify_account_create has been sent to AIME."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED)
        project_user.aime_confirmation_sent_at = datetime.now(UTC)

    @staticmethod
    def mark_covered_by_project(project_user: ProjectUser) -> None:
        """Set state when PI account is covered by notify_project_create."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT)
        if project_user.aime_confirmation_sent_at is None:
            project_user.aime_confirmation_sent_at = datetime.now(UTC)

    @staticmethod
    def _role_is_pi(role: str | None) -> bool:
        return str(role or "").strip().lower() == "pi"

    @staticmethod
    def _packet_type_for_rec_id(db: Session, packet_rec_id: int | None) -> str | None:
        if packet_rec_id is None:
            return None
        row = (
            db.query(AMIEPacket.packet_type)
            .filter(AMIEPacket.packet_rec_id == packet_rec_id)
            .first()
        )
        if row is None:
            return None
        return str(row[0]) if row[0] is not None else None

    def is_project_create_pi_membership(
        self,
        db: Session,
        project_user: ProjectUser,
    ) -> bool:
        if not self._role_is_pi(project_user.role):
            return False
        return (
            self._packet_type_for_rec_id(db, project_user.source_packet_rec_id)
            == "request_project_create"
        )

    def account_confirmation_required(
        self,
        db: Session,
        project_user: ProjectUser,
    ) -> bool:
        return not self.is_project_create_pi_membership(db, project_user)

    def _project_create_account_coverage_at(
        self,
        db: Session,
        project_user: ProjectUser,
    ) -> datetime | None:
        if not self.is_project_create_pi_membership(db, project_user):
            return None
        row = (
            db.query(OutboundPacketLog.sent_at)
            .filter(
                OutboundPacketLog.event_type == "notify_project_create",
                OutboundPacketLog.source_packet_rec_id == project_user.source_packet_rec_id,
                OutboundPacketLog.status == OutboundPacketLog.STATUS_SENT,
            )
            .order_by(OutboundPacketLog.sent_at.desc(), OutboundPacketLog.created_at.desc())
            .first()
        )
        if row is None:
            return None
        return row[0]

    def _mark_project_create_pi_memberships_covered(
        self,
        db: Session,
        project: Project,
        *,
        covered_at: datetime | None = None,
    ) -> int:
        marked = 0
        effective_covered_at = covered_at or datetime.now(UTC)
        for membership in project.project_users:
            if not self.is_project_create_pi_membership(db, membership):
                continue
            if membership.account_state not in (
                ProjectUser.ACCOUNT_STATE_AIME_NOTIFIED,
                ProjectUser.ACCOUNT_STATE_COVERED_BY_PROJECT,
            ):
                self.mark_covered_by_project(membership)
                membership.aime_confirmation_sent_at = effective_covered_at
                marked += 1
        return marked

    def _find_source_packet_rec_id(
        self,
        db: Session,
        project_user: ProjectUser,
    ) -> int | None:
        """Find a source request_account_create packet for account confirmation."""
        source_site_name = self._project_user_site_name(project_user)
        site_filter = or_(
            AMIEPacket.remote_site_name == source_site_name,
            AMIEPacket.originating_site_name == source_site_name,
            AMIEPacket.local_site_name == source_site_name,
        )
        if project_user.source_packet_rec_id:
            return int(project_user.source_packet_rec_id)

        if project_user.source_trans_rec_id:
            by_trans = (
                db.query(AMIEPacket.packet_rec_id)
                .filter(
                    AMIEPacket.trans_rec_id == project_user.source_trans_rec_id,
                    AMIEPacket.packet_type == "request_account_create",
                    site_filter,
                )
                .order_by(AMIEPacket.packet_rec_id.desc())
                .first()
            )
            if by_trans is not None:
                return int(by_trans[0])

        packet_filters = [
            AMIENewUserPacket.user_person_id == project_user.user.person_id,
            site_filter,
        ]
        if project_user.project.site_project_id:
            packet_filters.append(
                AMIENewUserPacket.project_id == project_user.project.site_project_id
            )
        elif project_user.project.grant_number:
            packet_filters.append(
                AMIENewUserPacket.grant_number == project_user.project.grant_number
            )
        else:
            return None

        row = (
            db.query(AMIEPacket.packet_rec_id)
            .join(AMIENewUserPacket, AMIENewUserPacket.packet_id == AMIEPacket.id)
            .filter(*packet_filters)
            .order_by(AMIEPacket.packet_rec_id.desc())
            .first()
        )
        if row is None:
            return None
        return int(row[0])

    @staticmethod
    def _fallback_login(project_user: ProjectUser) -> str | None:
        # For notify_account_create we prefer the OAuth-resolved email identity.
        if project_user.user.email:
            return project_user.user.email
        if project_user.remote_site_login:
            return project_user.remote_site_login
        if project_user.user.remote_site_login:
            return project_user.user.remote_site_login
        return project_user.user.person_id

    @staticmethod
    def _project_user_site_name(project_user: ProjectUser) -> str:
        return (
            project_user.project.source_site_name
            or project_user.user.source_site_name
            or settings.amie_site_name
        )

    @staticmethod
    def _packet_to_dict(packet: Any) -> dict[str, Any]:
        if isinstance(packet, dict):
            return packet
        if hasattr(packet, "as_dict"):
            try:
                payload = packet.as_dict()
            except Exception:  # noqa: BLE001
                return {}
            if isinstance(payload, dict):
                return payload
        return {}

    @staticmethod
    def _clean_scalar(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _source_packet_field(cls, packet: Any, field_name: str) -> Any:
        payload = cls._packet_to_dict(packet)
        body = payload.get("body", {})
        if isinstance(body, dict) and body.get(field_name) not in (None, "", []):
            return body.get(field_name)

        body_obj = getattr(packet, "body", None)
        body_value = getattr(body_obj, field_name, None)
        if body_value not in (None, "", []):
            return body_value

        packet_value = getattr(packet, field_name, None)
        if packet_value not in (None, "", []):
            return packet_value

        return None

    @classmethod
    def _source_packet_project_id(cls, packet: Any) -> str | None:
        return cls._clean_scalar(cls._source_packet_field(packet, "ProjectID"))

    @classmethod
    def _source_packet_resource(cls, packet: Any) -> str | None:
        allocated_resource = cls._clean_scalar(
            cls._source_packet_field(packet, "AllocatedResource")
        )
        if allocated_resource:
            return allocated_resource

        resource_list = cls._source_packet_field(packet, "ResourceList")
        if isinstance(resource_list, (list, tuple)):
            for resource in resource_list:
                cleaned = cls._clean_scalar(resource)
                if cleaned:
                    return cleaned
        return cls._clean_scalar(resource_list)

    @classmethod
    def _source_packet_remote_login(cls, packet: Any) -> str | None:
        return cls._clean_scalar(
            cls._source_packet_field(packet, "UserRemoteSiteLogin")
        )

    @classmethod
    def _source_packet_string_list(cls, packet: Any, field_name: str) -> list[str]:
        value = cls._source_packet_field(packet, field_name)
        if isinstance(value, (list, tuple)):
            return [
                cleaned
                for item in value
                if (cleaned := cls._clean_scalar(item)) is not None
            ]
        cleaned = cls._clean_scalar(value)
        return [cleaned] if cleaned is not None else []

    @staticmethod
    def _normalize_mapping_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, (list, tuple)):
            return []
        return [item for item in value if isinstance(item, dict)]

    @classmethod
    def _source_packet_mapping_list(
        cls,
        packet: Any,
        field_name: str,
    ) -> list[dict[str, Any]]:
        return cls._normalize_mapping_list(cls._source_packet_field(packet, field_name))

    @classmethod
    def _mapping_site_person_id(cls, value: dict[str, Any]) -> str | None:
        for key in ("site_person_id", "SitePersonId", "SitePersonID"):
            cleaned = cls._clean_scalar(value.get(key))
            if cleaned:
                return cleaned
        return None

    def _send_account_confirmation_packet(
        self,
        db: Session,
        *,
        project_user: ProjectUser,
        amie_client: AMIEClient,
    ) -> bool:
        """Send NotifyAccountCreate confirmation packet to AIME."""
        if project_user.aime_confirmation_sent_at is not None:
            return True

        source_packet_rec_id = self._find_source_packet_rec_id(db, project_user)
        if source_packet_rec_id is None:
            logger.warning(
                "Cannot send account confirmation: missing source packet for project_user=%s",
                project_user.id,
            )
            return False

        outbound = None
        try:
            _log_amie_interaction(
                "get_packet.start",
                site_name=self._project_user_site_name(project_user),
                project_user_id=project_user.id,
                source_packet_rec_id=source_packet_rec_id,
            )
            source_packet = amie_client.get_packet(packet_rec_id=source_packet_rec_id)
            _log_amie_interaction(
                "get_packet.finish",
                site_name=self._project_user_site_name(project_user),
                project_user_id=project_user.id,
                source_packet_rec_id=source_packet_rec_id,
            )

            project_id = (
                project_user.project.site_project_id
                or self._source_packet_project_id(source_packet)
            )
            resource = (
                project_user.resource
                or project_user.project.resource_type
                or self._source_packet_resource(source_packet)
            )
            remote_login = self._fallback_login(
                project_user
            ) or self._source_packet_remote_login(source_packet)

            recovered_fields: list[str] = []
            if project_id and not project_user.project.site_project_id:
                project_user.project.site_project_id = project_id
                recovered_fields.append("project_id")
            if resource and not project_user.project.resource_type:
                project_user.project.resource_type = resource
                recovered_fields.append("project_resource_type")
            if resource and not project_user.resource:
                project_user.resource = resource
                recovered_fields.append("project_user_resource")
            if remote_login and not project_user.remote_site_login:
                project_user.remote_site_login = remote_login
                recovered_fields.append("remote_login")

            if recovered_fields:
                _log_amie_interaction(
                    "account_confirmation.backfilled_fields",
                    project_user_id=project_user.id,
                    source_packet_rec_id=source_packet_rec_id,
                    recovered_fields=",".join(recovered_fields),
                    project_id=project_id,
                    resource=resource,
                    remote_login=remote_login,
                )

            if not project_id or not resource or not remote_login:
                logger.warning(
                    "Cannot send account confirmation: missing required fields "
                    "project_id=%s resource=%s remote_login=%s project_user=%s",
                    project_id,
                    resource,
                    remote_login,
                    project_user.id,
                )
                return False

            nac = source_packet.reply_packet(packet_type="notify_account_create")
            nac.AccountActivityTime = datetime.now(UTC)
            nac.ProjectID = project_id
            nac.ResourceList = [resource]
            nac.UserRemoteSiteLogin = remote_login

            outbound = OutboundPacketService.start_or_resume(
                db,
                event_type="notify_account_create",
                source_packet_rec_id=source_packet_rec_id,
                source_trans_rec_id=project_user.source_trans_rec_id,
                source_transaction_id=project_user.source_transaction_id,
                project_user_id=project_user.id,
                payload={
                    "packet_type": "notify_account_create",
                    "project_id": project_id,
                    "resource": resource,
                    "user_person_id": project_user.user.person_id,
                    "remote_site_login": remote_login,
                },
                worker_name="aime-worker",
            )
            if OutboundPacketService.is_locked(outbound):
                logger.warning(
                    "Outbound notify_account_create is locked for project_user=%s until %s",
                    project_user.id,
                    outbound.locked_until,
                )
                return False

            if project_user.user.person_id:
                nac.UserPersonID = project_user.user.person_id
            if project_user.user.first_name:
                nac.UserFirstName = project_user.user.first_name
            if project_user.user.last_name:
                nac.UserLastName = project_user.user.last_name
            if project_user.user.organization:
                nac.UserOrganization = project_user.user.organization
            if project_user.user.org_code:
                nac.UserOrgCode = project_user.user.org_code

            _log_amie_interaction(
                "send_packet.start",
                site_name=self._project_user_site_name(project_user),
                project_user_id=project_user.id,
                packet_type="notify_account_create",
                source_packet_rec_id=source_packet_rec_id,
            )
            send_result = amie_client.send_packet(nac)
            outbound_packet_rec_id = getattr(send_result, "packet_rec_id", None)
            _log_amie_interaction(
                "send_packet.finish",
                site_name=self._project_user_site_name(project_user),
                project_user_id=project_user.id,
                packet_type="notify_account_create",
                source_packet_rec_id=source_packet_rec_id,
                outbound_packet_rec_id=outbound_packet_rec_id,
            )
            OutboundPacketService.mark_sent(db, outbound, send_result=send_result)
            if outbound.outbound_packet_rec_id is not None:
                try:
                    _log_amie_interaction(
                        "get_packet.start",
                        site_name=self._project_user_site_name(project_user),
                        project_user_id=project_user.id,
                        outbound_packet_rec_id=outbound.outbound_packet_rec_id,
                    )
                    outbound_packet = amie_client.get_packet(packet_rec_id=outbound.outbound_packet_rec_id)
                    _log_amie_interaction(
                        "get_packet.finish",
                        site_name=self._project_user_site_name(project_user),
                        project_user_id=project_user.id,
                        outbound_packet_rec_id=outbound.outbound_packet_rec_id,
                    )
                    header = (
                        outbound_packet.get("header")
                        if isinstance(outbound_packet, dict)
                        else getattr(outbound_packet, "header", {})
                    )
                    transaction_state = (
                        header.get("transaction_state")
                        if isinstance(header, dict)
                        else getattr(header, "transaction_state", None)
                    )
                    packet_state = (
                        header.get("packet_state")
                        if isinstance(header, dict)
                        else getattr(header, "packet_state", None)
                    )
                    acked = str(transaction_state or "").lower() in {
                        "complete",
                        "completed",
                        "done",
                    } or str(packet_state or "").lower() in {"processed", "complete"}
                    _log_amie_interaction(
                        "mark_outbound_ack",
                        site_name=self._project_user_site_name(project_user),
                        project_user_id=project_user.id,
                        outbound_packet_rec_id=outbound.outbound_packet_rec_id,
                        acked=acked,
                        transaction_state=transaction_state,
                        packet_state=packet_state,
                    )
                    OutboundPacketService.mark_acked(db, outbound, acked=acked)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to refresh outbound ack status for outbound_packet_rec_id=%s",
                        outbound.outbound_packet_rec_id,
                    )

            self.mark_aime_notified(project_user)
            project_user.source_packet_rec_id = source_packet_rec_id
            logger.info(
                "Sent notify_account_create confirmation for project_user=%s source_packet_rec_id=%s",
                project_user.id,
                source_packet_rec_id,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Failed to send notify_account_create for project_user=%s source_packet_rec_id=%s",
                project_user.id,
                source_packet_rec_id,
            )
            OutboundPacketService.safe_mark_failed(
                db,
                row=outbound,
                event_type="notify_account_create",
                error_message=str(exc),
                project_user_id=project_user.id,
            )
            return False

    def _invite_completion_allows_confirmation(
        self,
        db: Session,
        project_user: ProjectUser,
    ) -> bool:
        """Return whether invite email dispatch and OAuth completion are done."""
        if project_user.account_state != ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH:
            return False
        if project_user.email_sent_at is None:
            return False
        if project_user.account_made_at is None:
            return False
        if project_user.account_made_at < project_user.email_sent_at:
            return False

        invite = (
            db.query(ProjectInvite.id)
            .filter(
                ProjectInvite.status == ProjectInvite.STATUS_USED,
                ProjectInvite.user_id == project_user.user_id,
                or_(
                    ProjectInvite.project_id == project_user.project_id,
                    ProjectInvite.project_id.is_(None),
                ),
                ProjectInvite.events.any(
                    ProjectInviteEvent.event_type == "invite_email_dispatched"
                ),
            )
            .order_by(ProjectInvite.used_at.desc())
            .first()
        )
        return invite is not None

    def reconcile_pending_confirmations(self, db: Session) -> dict[str, int]:
        """Send AIME confirmations for account rows where OAuth is complete."""
        review_states = (ProjectUser.ACCOUNT_STATE_USER_COMPLETED_OAUTH,)
        review_accounts = (
            db.query(ProjectUser)
            .options(joinedload(ProjectUser.user), joinedload(ProjectUser.project))
            .filter(
                ProjectUser.is_active.is_(True),
                ProjectUser.account_state.in_(review_states),
            )
            .all()
        )

        checked = 0
        transitioned = 0
        confirmations_sent = 0
        failures = 0
        deferred = 0

        can_send_confirmation = bool(
            settings.amie_account_confirmation_enabled and settings.amie_api_key
        )

        if not can_send_confirmation and settings.amie_account_confirmation_enabled:
            logger.debug(
                "AIME confirmation is enabled but AMIE_API_KEY is missing; confirmations will be deferred"
            )

        with ExitStack() as stack:
            amie_clients_by_site: dict[str, AMIEClient] = {}
            configured_sites = configured_amie_site_names()
            for project_user in review_accounts:
                checked += 1
                try:
                    if (
                        can_send_confirmation
                        and project_user.aime_confirmation_sent_at is None
                    ):
                        if not self.account_confirmation_required(db, project_user):
                            covered_at = self._project_create_account_coverage_at(
                                db, project_user
                            )
                            if covered_at is not None:
                                self.mark_covered_by_project(project_user)
                                project_user.aime_confirmation_sent_at = covered_at
                                _log_amie_interaction(
                                    "account_confirmation.covered_by_project_create",
                                    project_user_id=project_user.id,
                                    site_name=self._project_user_site_name(project_user),
                                    source_packet_rec_id=project_user.source_packet_rec_id,
                                    covered_at=covered_at.isoformat(),
                                )
                            else:
                                deferred += 1
                                _log_amie_interaction(
                                    "account_confirmation.deferred_project_create_cover_pending",
                                    project_user_id=project_user.id,
                                    site_name=self._project_user_site_name(project_user),
                                    source_packet_rec_id=project_user.source_packet_rec_id,
                                )
                            db.commit()
                            continue

                        if not self._invite_completion_allows_confirmation(
                            db, project_user
                        ):
                            deferred += 1
                            _log_amie_interaction(
                                "account_confirmation.deferred_invite_incomplete",
                                project_user_id=project_user.id,
                                site_name=self._project_user_site_name(project_user),
                                email_sent_at=project_user.email_sent_at,
                                account_made_at=project_user.account_made_at,
                            )
                            db.commit()
                            continue

                        if not project_user.project.site_project_id:
                            deferred += 1
                            _log_amie_interaction(
                                "account_confirmation.deferred_project_not_provisioned",
                                project_user_id=project_user.id,
                                site_name=self._project_user_site_name(project_user),
                                project_id=str(project_user.project.id),
                            )
                            db.commit()
                            continue

                        source_site_name = self._project_user_site_name(project_user)
                        if source_site_name not in amie_clients_by_site:
                            if source_site_name not in configured_sites:
                                logger.warning(
                                    "Account confirmation for project_user=%s uses site=%s not in AMIE_SITE_NAMES; opening ad-hoc client",
                                    project_user.id,
                                    source_site_name,
                                )
                            amie_clients_by_site[source_site_name] = stack.enter_context(
                                AMIEClient(
                                    site_name=source_site_name,
                                    api_key=settings.amie_api_key,
                                    amie_url=settings.amie_url,
                                )
                            )
                            _log_amie_interaction(
                                "client.opened",
                                site_name=source_site_name,
                                project_user_id=project_user.id,
                            )
                        if self._send_account_confirmation_packet(
                            db,
                            project_user=project_user,
                            amie_client=amie_clients_by_site[source_site_name],
                        ):
                            confirmations_sent += 1
                        else:
                            failures += 1

                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()
                    failures += 1
                    logger.exception(
                        "Failed account lifecycle reconciliation for project_user=%s",
                        project_user.id,
                    )

        return {
            "checked": checked,
            "transitioned": transitioned,
            "confirmations_sent": confirmations_sent,
            "failures": failures,
            "deferred": deferred,
        }

    def reconcile_pending_project_notifications(
        self, db: Session
    ) -> dict[str, int]:
        """Send notify_project_create packets for provisioned projects.

        Finds every project in the ``ready`` state that has a source packet
        but has not yet had a ``notify_project_create`` outbound record
        successfully sent, then sends the reply packet.
        """
        ready_projects = (
            db.query(Project)
            .filter(
                Project.is_active.is_(True),
                Project.lifecycle_state == Project.LIFECYCLE_STATE_PROVISIONED,
                Project.source_packet_rec_id.isnot(None),
            )
            .all()
        )

        checked = 0
        notifications_sent = 0
        already_sent = 0
        failures = 0
        deferred = 0

        can_send = bool(settings.amie_account_confirmation_enabled and settings.amie_api_key)

        for project in ready_projects:
            checked += 1
            site_name = str(project.source_site_name or settings.amie_site_name or "NRP")
            source_packet_record = (
                db.query(AMIEPacket)
                .options(joinedload(AMIEPacket.allocation_packet))
                .filter(AMIEPacket.packet_rec_id == project.source_packet_rec_id)
                .first()
            )
            allocation_packet = (
                source_packet_record.allocation_packet
                if source_packet_record is not None
                else None
            )

            # Check whether we already have a successful outbound record for
            # this source packet to avoid double-sending across worker cycles.
            existing = (
                db.query(OutboundPacketLog)
                .filter(
                    OutboundPacketLog.event_type == "notify_project_create",
                    OutboundPacketLog.source_packet_rec_id == project.source_packet_rec_id,
                    OutboundPacketLog.status.in_(
                        [OutboundPacketLog.STATUS_SENT, OutboundPacketLog.STATUS_PENDING]
                    ),
                )
                .first()
            )

            if existing is not None:
                if existing.status == OutboundPacketLog.STATUS_SENT:
                    covered_count = self._mark_project_create_pi_memberships_covered(
                        db,
                        project,
                        covered_at=existing.sent_at,
                    )
                    if covered_count:
                        _log_amie_interaction(
                            "project_notification.covered_pi_accounts",
                            project_id=project.id,
                            site_name=site_name,
                            source_packet_rec_id=project.source_packet_rec_id,
                            membership_count=covered_count,
                        )
                        db.commit()
                already_sent += 1
                _log_amie_interaction(
                    "project_notification.already_sent",
                    project_id=project.id,
                    site_name=site_name,
                    source_packet_rec_id=project.source_packet_rec_id,
                    outbound_status=existing.status,
                )
                continue

            if not can_send:
                _log_amie_interaction(
                    "project_notification.deferred_no_api_key",
                    project_id=project.id,
                    site_name=site_name,
                    source_packet_rec_id=project.source_packet_rec_id,
                )
                continue

            outbound = None
            try:
                _log_amie_interaction(
                    "project_notification.get_packet.start",
                    project_id=project.id,
                    site_name=site_name,
                    source_packet_rec_id=project.source_packet_rec_id,
                )
                with AMIEClient(
                    site_name=site_name,
                    api_key=settings.amie_api_key,
                    amie_url=settings.amie_url,
                ) as amie_client:
                    source_packet = amie_client.get_packet(packet_rec_id=project.source_packet_rec_id)
                    _log_amie_interaction(
                        "project_notification.get_packet.finish",
                        project_id=project.id,
                        site_name=site_name,
                        source_packet_rec_id=project.source_packet_rec_id,
                    )

                    grant_number = (
                        project.grant_number
                        or self._clean_scalar(
                            self._source_packet_field(source_packet, "GrantNumber")
                        )
                        or self._clean_scalar(
                            allocation_packet.grant_number if allocation_packet else None
                        )
                    )
                    project_site_id = (
                        project.site_project_id
                        or self._source_packet_project_id(source_packet)
                    )
                    pfos_number = (
                        project.pfos_number
                        or self._clean_scalar(
                            self._source_packet_field(source_packet, "PfosNumber")
                        )
                        or self._clean_scalar(
                            allocation_packet.pfos_number if allocation_packet else None
                        )
                    )
                    resource = (
                        project.allocated_resource
                        or project.resource_type
                        or self._source_packet_resource(source_packet)
                    )
                    pi_user = next(
                        (pu for pu in project.project_users if pu.role == "pi"), None
                    )
                    pi_remote_login = (
                        (
                            pi_user.remote_site_login
                            or (pi_user.user.remote_site_login if pi_user.user else None)
                        )
                        if pi_user
                        else None
                    )
                    pi_person_id = (
                        project.pi_person_id
                        or self._clean_scalar(
                            self._source_packet_field(source_packet, "PiPersonID")
                        )
                        or self._clean_scalar(
                            allocation_packet.pi_person_id if allocation_packet else None
                        )
                    )
                    pi_global_id = self._clean_scalar(
                        self._source_packet_field(source_packet, "PiGlobalID")
                    ) or self._clean_scalar(
                        allocation_packet.pi_global_id if allocation_packet else None
                    )
                    pi_dn_list = self._source_packet_string_list(source_packet, "PiDnList") or (
                        [
                            item
                            for item in (allocation_packet.pi_dn_list or [])
                            if isinstance(item, str) and item.strip()
                        ]
                        if allocation_packet is not None
                        else []
                    )
                    pi_requested_login_list = self._source_packet_string_list(
                        source_packet, "PiRequestedLoginList"
                    ) or (
                        [
                            item
                            for item in (allocation_packet.pi_requested_login_list or [])
                            if isinstance(item, str) and item.strip()
                        ]
                        if allocation_packet is not None
                        else []
                    )
                    site_person_ids = self._source_packet_mapping_list(
                        source_packet, "SitePersonId"
                    ) or (
                        self._normalize_mapping_list(allocation_packet.site_person_ids)
                        if allocation_packet is not None
                        else []
                    )
                    has_site_person_id = any(
                        self._mapping_site_person_id(item) for item in site_person_ids
                    )
                    if not pi_remote_login:
                        deferred += 1
                        _log_amie_interaction(
                            "project_notification.deferred_pi_login_missing",
                            project_id=project.id,
                            site_name=site_name,
                            source_packet_rec_id=project.source_packet_rec_id,
                        )
                        db.commit()
                        continue

                    if not pi_person_id:
                        deferred += 1
                        _log_amie_interaction(
                            "project_notification.deferred_pi_person_id_missing",
                            project_id=project.id,
                            site_name=site_name,
                            source_packet_rec_id=project.source_packet_rec_id,
                        )
                        db.commit()
                        continue

                    if not has_site_person_id:
                        deferred += 1
                        _log_amie_interaction(
                            "project_notification.deferred_site_person_id_missing",
                            project_id=project.id,
                            site_name=site_name,
                            source_packet_rec_id=project.source_packet_rec_id,
                            pi_person_id=pi_person_id,
                        )
                        db.commit()
                        continue

                    if not grant_number or not project_site_id or not resource:
                        deferred += 1
                        _log_amie_interaction(
                            "project_notification.deferred_required_fields_missing",
                            project_id=project.id,
                            site_name=site_name,
                            source_packet_rec_id=project.source_packet_rec_id,
                            grant_number=grant_number,
                            project_site_id=project_site_id,
                            resource=resource,
                            pi_person_id=pi_person_id,
                            pi_remote_login=pi_remote_login,
                        )
                        db.commit()
                        continue

                    npc = source_packet.reply_packet(packet_type="notify_project_create")
                    npc.GrantNumber = grant_number
                    npc.ProjectID = project_site_id
                    npc.PfosNumber = pfos_number
                    npc.ResourceList = [resource] if resource else []
                    npc.PiPersonID = pi_person_id
                    npc.PiGlobalID = pi_global_id
                    npc.PiFirstName = project.pi_first_name
                    npc.PiMiddleName = project.pi_middle_name
                    npc.PiLastName = project.pi_last_name
                    npc.PiEmail = project.pi_email
                    npc.PiOrganization = project.pi_organization
                    npc.PiOrgCode = project.pi_org_code
                    npc.PiDepartment = project.pi_department
                    npc.PiBusinessPhoneNumber = project.pi_business_phone_number
                    npc.PiDnList = pi_dn_list
                    npc.PiRequestedLoginList = pi_requested_login_list
                    npc.PiRemoteSiteLogin = pi_remote_login
                    npc.SitePersonId = site_person_ids

                    outbound = OutboundPacketService.start_or_resume(
                        db,
                        event_type="notify_project_create",
                        source_packet_rec_id=project.source_packet_rec_id,
                        source_trans_rec_id=project.source_trans_rec_id,
                        source_transaction_id=project.source_transaction_id,
                        payload={
                            "packet_type": "notify_project_create",
                            "project_id": str(project.id),
                            "site_project_id": project_site_id,
                            "aime_allocation_id": project.aime_allocation_id,
                            "grant_number": grant_number,
                            "pfos_number": pfos_number,
                        },
                        worker_name="aime-worker",
                    )

                    _log_amie_interaction(
                        "project_notification.send_packet.start",
                        project_id=project.id,
                        site_name=site_name,
                        source_packet_rec_id=project.source_packet_rec_id,
                    )
                    send_result = amie_client.send_packet(npc)
                    outbound_packet_rec_id = getattr(send_result, "packet_rec_id", None)
                    _log_amie_interaction(
                        "project_notification.send_packet.finish",
                        project_id=project.id,
                        site_name=site_name,
                        source_packet_rec_id=project.source_packet_rec_id,
                        outbound_packet_rec_id=outbound_packet_rec_id,
                    )
                    OutboundPacketService.mark_sent(db, outbound, send_result=send_result)
                    covered_count = self._mark_project_create_pi_memberships_covered(
                        db,
                        project,
                        covered_at=outbound.sent_at,
                    )
                    if covered_count:
                        _log_amie_interaction(
                            "project_notification.covered_pi_accounts",
                            project_id=project.id,
                            site_name=site_name,
                            source_packet_rec_id=project.source_packet_rec_id,
                            membership_count=covered_count,
                        )
                    project.set_lifecycle_state(Project.LIFECYCLE_STATE_AIME_NOTIFIED)
                    notifications_sent += 1
                    db.commit()
                    logger.info(
                        "Sent notify_project_create for project=%s source_packet_rec_id=%s",
                        project.id,
                        project.source_packet_rec_id,
                    )

            except Exception as exc:  # noqa: BLE001
                db.rollback()
                failures += 1
                logger.exception(
                    "Failed to send notify_project_create for project=%s source_packet_rec_id=%s",
                    project.id,
                    project.source_packet_rec_id,
                )
                OutboundPacketService.safe_mark_failed(
                    db,
                    row=outbound,
                    event_type="notify_project_create",
                    error_message=str(exc),
                )

        return {
            "checked": checked,
            "notifications_sent": notifications_sent,
            "already_sent": already_sent,
            "failures": failures,
            "deferred": deferred,
        }
