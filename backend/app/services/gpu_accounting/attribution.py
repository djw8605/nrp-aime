"""Map an accounting ``created_by`` to the AMIE username charged for it.

People are identified by CILogon subject URLs (``User.remote_site_login``)
and must be members of the project; their usage is otherwise dropped.  Any
non-person creator (service accounts, ``system:*``, empty) is charged to the
project PI.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import settings
from app.models.gpu_usage_record import GpuUsageRecord
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User
from app.services.aime.logins import amie_login

CILOGON_SUBJECT_RE = re.compile(r"^https?://cilogon\.org/", re.IGNORECASE)


@dataclass(frozen=True)
class Attribution:
    """AMIE username to charge; ``""`` when the PI has no site login yet."""

    username: str
    attribution: str


def _preferred_login(memberships: Iterable[ProjectUser]) -> str | None:
    """Pick a site login, preferring GPU-resource and active memberships."""
    gpu_resource = settings.amie_gpu_resource_name
    with_login = [pu for pu in memberships if (pu.remote_site_login or "").strip()]
    if not with_login:
        return None
    with_login.sort(
        key=lambda pu: (
            gpu_resource not in (pu.resource, pu.allocated_resource),
            not pu.is_active,
        )
    )
    return amie_login(with_login[0].remote_site_login)


class GpuUsageAttributor:
    """Resolves usage rows to AMIE usernames for one sync cycle."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._member_logins: dict[tuple[uuid.UUID, str], str | None] = {}

    @staticmethod
    def is_person(created_by: str) -> bool:
        return bool(CILOGON_SUBJECT_RE.match(created_by or ""))

    def attribute(self, project: Project, created_by: str) -> Attribution | None:
        """Return who to charge for *created_by* in *project*; None means drop."""
        if self.is_person(created_by):
            login = self._member_login(project, created_by)
            if login is None:
                return None
            return Attribution(login, GpuUsageRecord.ATTRIBUTION_MEMBER)
        return Attribution(self._pi_login(project) or "", GpuUsageRecord.ATTRIBUTION_PI)

    def _member_login(self, project: Project, cilogon_id: str) -> str | None:
        key = (project.id, cilogon_id)
        if key not in self._member_logins:
            memberships = (
                self.db.query(ProjectUser)
                .join(User, User.id == ProjectUser.user_id)
                .filter(
                    ProjectUser.project_id == project.id,
                    User.remote_site_login == cilogon_id,
                )
                .all()
            )
            self._member_logins[key] = _preferred_login(memberships)
        return self._member_logins[key]

    @staticmethod
    def _pi_login(project: Project) -> str | None:
        pis = [
            pu
            for pu in project.project_users
            if str(pu.role or "").strip().lower() == "pi"
        ]
        return _preferred_login(pis)
