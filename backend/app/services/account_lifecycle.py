"""Project-user account lifecycle management."""

from __future__ import annotations

from contextlib import ExitStack
import logging
from datetime import UTC, datetime

from amieclient import AMIEClient
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.config import configured_amie_site_names, settings
from app.models.amie_new_user_packet import AMIENewUserPacket
from app.models.amie_packet import AMIEPacket
from app.models.project_user import ProjectUser
from app.services.outbound_packets import OutboundPacketService

logger = logging.getLogger(__name__)


class AccountLifecycleService:
    """Handle account state transitions and AIME confirmation packets."""

    def __init__(self) -> None:
        """Initialize account lifecycle service."""

    @staticmethod
    def mark_just_received(
        project_user: ProjectUser,
        *,
        source_packet_rec_id: int | None = None,
    ) -> None:
        """Set state for newly received account requests."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_JUST_RECEIVED_PACKET)
        if source_packet_rec_id is not None:
            project_user.source_packet_rec_id = source_packet_rec_id

    @staticmethod
    def mark_email_sent(project_user: ProjectUser) -> None:
        """Set state when account creation email has been sent."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_SENT_EMAIL)
        project_user.email_sent_at = datetime.now(UTC)

    @staticmethod
    def mark_account_made(project_user: ProjectUser) -> None:
        """Set state when account existence has been confirmed."""
        project_user.set_account_state(ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE)
        if project_user.account_made_at is None:
            project_user.account_made_at = datetime.now(UTC)

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

        if not project_user.project.site_project_id:
            return None

        row = (
            db.query(AMIEPacket.packet_rec_id)
            .join(AMIENewUserPacket, AMIENewUserPacket.packet_id == AMIEPacket.id)
            .filter(
                AMIENewUserPacket.project_id == project_user.project.site_project_id,
                AMIENewUserPacket.user_person_id == project_user.user.person_id,
                site_filter,
            )
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

        project_id = project_user.project.site_project_id
        resource = project_user.resource or project_user.project.resource_type
        remote_login = self._fallback_login(project_user)

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

        outbound = None
        try:
            source_packet = amie_client.get_packet(source_packet_rec_id)
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

            send_result = amie_client.send_packet(nac)
            OutboundPacketService.mark_sent(db, outbound, send_result=send_result)
            if outbound.outbound_packet_rec_id is not None:
                try:
                    outbound_packet = amie_client.get_packet(outbound.outbound_packet_rec_id)
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
                    OutboundPacketService.mark_acked(db, outbound, acked=acked)
                except Exception:  # noqa: BLE001
                    logger.exception(
                        "Failed to refresh outbound ack status for outbound_packet_rec_id=%s",
                        outbound.outbound_packet_rec_id,
                    )

            project_user.aime_confirmation_sent_at = datetime.now(UTC)
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

    def reconcile_pending_confirmations(self, db: Session) -> dict[str, int]:
        """Send AIME confirmations for account rows already marked account_made."""
        review_states = (ProjectUser.ACCOUNT_STATE_ACCOUNT_MADE,)
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
        }
