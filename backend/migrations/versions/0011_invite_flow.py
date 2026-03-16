"""Add project invite onboarding tables.

Revision ID: 0011_invite_flow
Revises: 0010_ops_observability
Create Date: 2026-03-16 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0011_invite_flow"
down_revision = "0010_ops_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "project_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invited_by", sa.String(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("authentik_group_name", sa.String(), nullable=True),
        sa.Column("redirect_path", sa.String(), nullable=True),
        sa.Column(
            "invite_metadata",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_project_invites_project_id"),
        "project_invites",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invites_email"),
        "project_invites",
        ["email"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invites_status"),
        "project_invites",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invites_expires_at"),
        "project_invites",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "project_invite_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invite_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "event_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'info'"),
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "event_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["invite_id"], ["project_invites.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_project_invite_events_invite_id"),
        "project_invite_events",
        ["invite_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invite_events_event_type"),
        "project_invite_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invite_events_event_status"),
        "project_invite_events",
        ["event_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_invite_events_created_at"),
        "project_invite_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(
        op.f("ix_project_invite_events_created_at"),
        table_name="project_invite_events",
    )
    op.drop_index(
        op.f("ix_project_invite_events_event_status"),
        table_name="project_invite_events",
    )
    op.drop_index(
        op.f("ix_project_invite_events_event_type"),
        table_name="project_invite_events",
    )
    op.drop_index(
        op.f("ix_project_invite_events_invite_id"),
        table_name="project_invite_events",
    )
    op.drop_table("project_invite_events")

    op.drop_index(op.f("ix_project_invites_expires_at"), table_name="project_invites")
    op.drop_index(op.f("ix_project_invites_status"), table_name="project_invites")
    op.drop_index(op.f("ix_project_invites_email"), table_name="project_invites")
    op.drop_index(op.f("ix_project_invites_project_id"), table_name="project_invites")
    op.drop_table("project_invites")
