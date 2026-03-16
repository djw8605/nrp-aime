"""Add observability, retry, and outbound tracking tables.

Revision ID: 0010_ops_observability
Revises: 0009_packet_log_status
Create Date: 2026-03-15 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0010_ops_observability"
down_revision = "0009_packet_log_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "amie_packets",
        sa.Column(
            "ingest_source",
            sa.String(),
            nullable=False,
            server_default=sa.text("'worker'"),
        ),
    )
    op.add_column(
        "amie_packets",
        sa.Column(
            "reprocess_attempt_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "amie_packets",
        sa.Column("reprocess_last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "amie_packets",
        sa.Column("reprocess_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "amie_packets",
        sa.Column("reprocess_last_error", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_amie_packets_ingest_source"),
        "amie_packets",
        ["ingest_source"],
        unique=False,
    )

    op.add_column(
        "worker_statuses",
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "worker_statuses",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "worker_statuses",
        sa.Column("last_error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        op.f("ix_worker_statuses_last_success_at"),
        "worker_statuses",
        ["last_success_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_worker_statuses_last_error_at"),
        "worker_statuses",
        ["last_error_at"],
        unique=False,
    )

    op.create_table(
        "outbound_packet_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_name", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("ack_status", sa.String(), nullable=False, server_default=sa.text("'unknown'")),
        sa.Column("source_packet_rec_id", sa.BigInteger(), nullable=True),
        sa.Column("source_trans_rec_id", sa.BigInteger(), nullable=True),
        sa.Column("source_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("outbound_packet_rec_id", sa.BigInteger(), nullable=True),
        sa.Column("outbound_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("project_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["project_user_id"], ["project_users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_worker_name"),
        "outbound_packet_logs",
        ["worker_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_event_type"),
        "outbound_packet_logs",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_status"),
        "outbound_packet_logs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_ack_status"),
        "outbound_packet_logs",
        ["ack_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_source_packet_rec_id"),
        "outbound_packet_logs",
        ["source_packet_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_source_trans_rec_id"),
        "outbound_packet_logs",
        ["source_trans_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_source_transaction_id"),
        "outbound_packet_logs",
        ["source_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_outbound_packet_rec_id"),
        "outbound_packet_logs",
        ["outbound_packet_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_outbound_transaction_id"),
        "outbound_packet_logs",
        ["outbound_transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outbound_packet_logs_project_user_id"),
        "outbound_packet_logs",
        ["project_user_id"],
        unique=False,
    )

    op.create_table(
        "alert_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_key", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("send_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_key"),
    )
    op.create_index(
        op.f("ix_alert_notifications_alert_key"),
        "alert_notifications",
        ["alert_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_alert_notifications_category"),
        "alert_notifications",
        ["category"],
        unique=False,
    )
    op.create_index(
        op.f("ix_alert_notifications_severity"),
        "alert_notifications",
        ["severity"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(op.f("ix_alert_notifications_severity"), table_name="alert_notifications")
    op.drop_index(op.f("ix_alert_notifications_category"), table_name="alert_notifications")
    op.drop_index(op.f("ix_alert_notifications_alert_key"), table_name="alert_notifications")
    op.drop_table("alert_notifications")

    op.drop_index(
        op.f("ix_outbound_packet_logs_project_user_id"),
        table_name="outbound_packet_logs",
    )
    op.drop_index(
        op.f("ix_outbound_packet_logs_outbound_transaction_id"),
        table_name="outbound_packet_logs",
    )
    op.drop_index(
        op.f("ix_outbound_packet_logs_outbound_packet_rec_id"),
        table_name="outbound_packet_logs",
    )
    op.drop_index(
        op.f("ix_outbound_packet_logs_source_transaction_id"),
        table_name="outbound_packet_logs",
    )
    op.drop_index(
        op.f("ix_outbound_packet_logs_source_trans_rec_id"),
        table_name="outbound_packet_logs",
    )
    op.drop_index(
        op.f("ix_outbound_packet_logs_source_packet_rec_id"),
        table_name="outbound_packet_logs",
    )
    op.drop_index(op.f("ix_outbound_packet_logs_ack_status"), table_name="outbound_packet_logs")
    op.drop_index(op.f("ix_outbound_packet_logs_status"), table_name="outbound_packet_logs")
    op.drop_index(op.f("ix_outbound_packet_logs_event_type"), table_name="outbound_packet_logs")
    op.drop_index(op.f("ix_outbound_packet_logs_worker_name"), table_name="outbound_packet_logs")
    op.drop_table("outbound_packet_logs")

    op.drop_index(op.f("ix_worker_statuses_last_error_at"), table_name="worker_statuses")
    op.drop_index(op.f("ix_worker_statuses_last_success_at"), table_name="worker_statuses")
    op.drop_column("worker_statuses", "last_error_message")
    op.drop_column("worker_statuses", "last_error_at")
    op.drop_column("worker_statuses", "last_success_at")

    op.drop_index(op.f("ix_amie_packets_ingest_source"), table_name="amie_packets")
    op.drop_column("amie_packets", "reprocess_last_error")
    op.drop_column("amie_packets", "reprocess_locked_until")
    op.drop_column("amie_packets", "reprocess_last_attempt_at")
    op.drop_column("amie_packets", "reprocess_attempt_count")
    op.drop_column("amie_packets", "ingest_source")
