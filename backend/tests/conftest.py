"""Shared fixtures for lifecycle tests.

Uses an in-memory SQLite database so tests run without PostgreSQL.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models.project import Project
from app.models.project_user import ProjectUser
from app.models.user import User


@pytest.fixture()
def db():
    """Yield an in-memory SQLite session with all tables created."""
    engine = create_engine("sqlite:///:memory:")

    # SQLite doesn't have a native UUID type; store as string.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Remove the hard-delete listener so we can freely clean up in tests.
    if event.contains(Project, "before_delete", _get_hard_delete_listener()):
        event.remove(Project, "before_delete", _get_hard_delete_listener())

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _get_hard_delete_listener():
    """Return the hard-delete listener function from the Project module."""
    from app.models.project import _prevent_project_hard_delete
    return _prevent_project_hard_delete


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def make_project():
    """Factory that creates a Project with sensible defaults."""
    def _make(db: Session, **overrides) -> Project:
        defaults = {
            "aime_allocation_id": f"ALLOC-{uuid.uuid4().hex[:8]}",
            "name": f"Test Project {uuid.uuid4().hex[:6]}",
            "is_active": True,
        }
        defaults.update(overrides)
        project = Project(**defaults)
        db.add(project)
        db.flush()
        return project
    return _make


@pytest.fixture()
def make_user():
    """Factory that creates a User with sensible defaults."""
    def _make(db: Session, **overrides) -> User:
        defaults = {
            "email": f"user-{uuid.uuid4().hex[:8]}@example.com",
            "name": f"Test User {uuid.uuid4().hex[:6]}",
            "is_active": True,
        }
        defaults.update(overrides)
        user = User(**defaults)
        db.add(user)
        db.flush()
        return user
    return _make


@pytest.fixture()
def make_project_user():
    """Factory that creates a ProjectUser with sensible defaults."""
    def _make(
        db: Session,
        project: Project,
        user: User,
        **overrides,
    ) -> ProjectUser:
        defaults = {
            "project_id": project.id,
            "user_id": user.id,
            "is_active": True,
            "account_state": ProjectUser.ACCOUNT_STATE_RECEIVED,
            "account_state_updated_at": datetime.now(UTC),
        }
        defaults.update(overrides)
        pu = ProjectUser(**defaults)
        db.add(pu)
        db.flush()
        return pu
    return _make
