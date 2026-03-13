"""AIME allocation ingestion service.

Wraps the ``amieclient`` library and translates incoming AMIE allocation
packets into database records (Projects and Users).
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User

logger = logging.getLogger(__name__)


class AIMEService:
    """Translates AMIE allocation packets into database records."""

    def __init__(self, site_name: str) -> None:
        self.site_name = site_name

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_or_create_user(self, db: Session, email: str, name: str) -> User:
        """Return an existing User or create a new one."""
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(email=email, name=name)
            db.add(user)
            db.flush()
            logger.info("Created new user: %s", email)
        return user

    def _get_or_create_project(
        self,
        db: Session,
        aime_allocation_id: str,
        name: str,
        resource_type: Optional[str],
        cpu_allocated: int,
        gpu_allocated: int,
        kubernetes_namespace: Optional[str],
    ) -> Project:
        """Return an existing Project or create a new one."""
        project = (
            db.query(Project)
            .filter(Project.aime_allocation_id == aime_allocation_id)
            .first()
        )
        if project is None:
            project = Project(
                aime_allocation_id=aime_allocation_id,
                name=name,
                resource_type=resource_type,
                cpu_allocated=cpu_allocated,
                gpu_allocated=gpu_allocated,
                kubernetes_namespace=kubernetes_namespace,
            )
            db.add(project)
            db.flush()
            logger.info("Created new project: %s (%s)", name, aime_allocation_id)
        return project

    def _assign_user_to_project(
        self, db: Session, project: Project, user: User, role: Optional[str] = None
    ) -> None:
        """Assign a user to a project if not already assigned."""
        existing = (
            db.query(ProjectUser)
            .filter(
                ProjectUser.project_id == project.id,
                ProjectUser.user_id == user.id,
            )
            .first()
        )
        if existing is None:
            pu = ProjectUser(project_id=project.id, user_id=user.id, role=role)
            db.add(pu)
            logger.info("Assigned user %s to project %s", user.email, project.name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_packet(self, db: Session, packet: dict) -> Project:
        """Process a raw AMIE allocation packet dictionary.

        Args:
            db: Active SQLAlchemy session.
            packet: Dictionary representation of an AMIE allocation packet.
                Expected keys:
                  - ``allocation_id`` (str)
                  - ``project_name`` (str)
                  - ``resource_type`` (str, optional)
                  - ``cpu`` (int, optional)
                  - ``gpu`` (int, optional)
                  - ``namespace`` (str, optional)
                  - ``users`` (list of dicts with ``email`` and ``name``)

        Returns:
            The created or updated :class:`~app.models.project.Project`.
        """
        project = self._get_or_create_project(
            db=db,
            aime_allocation_id=str(packet.get("allocation_id", "")),
            name=str(packet.get("project_name", "Unknown")),
            resource_type=packet.get("resource_type"),
            cpu_allocated=int(packet.get("cpu", 0)),
            gpu_allocated=int(packet.get("gpu", 0)),
            kubernetes_namespace=packet.get("namespace"),
        )

        for user_info in packet.get("users", []):
            user = self._get_or_create_user(
                db=db,
                email=user_info.get("email", ""),
                name=user_info.get("name", ""),
            )
            self._assign_user_to_project(db, project, user, role=user_info.get("role"))

        db.commit()
        return project
