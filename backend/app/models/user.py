"""User model."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """Represents an NRP user."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    person_id: Mapped[str | None] = mapped_column(
        String, unique=True, index=True, nullable=True
    )
    global_id: Mapped[str | None] = mapped_column(String, nullable=True)
    organization: Mapped[str | None] = mapped_column(String, nullable=True)
    org_code: Mapped[str | None] = mapped_column(String, nullable=True)
    department: Mapped[str | None] = mapped_column(String, nullable=True)
    nsf_status_code: Mapped[str | None] = mapped_column(String, nullable=True)
    dn_list: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    remote_site_login: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    project_users: Mapped[list["ProjectUser"]] = relationship(
        "ProjectUser", back_populates="user", cascade="all, delete-orphan"
    )
    invites: Mapped[list["ProjectInvite"]] = relationship(
        "ProjectInvite",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
