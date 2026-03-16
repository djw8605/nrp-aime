"""Add processing status fields to packet log table.

Revision ID: 0009_packet_log_status
Revises: 0008_unprocessed_packets
Create Date: 2026-03-14 23:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009_packet_log_status"
down_revision = "0008_unprocessed_packets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.add_column(
        "amie_packets",
        sa.Column(
            "processing_status",
            sa.String(),
            nullable=False,
            server_default=sa.text("'received'"),
        ),
    )
    op.add_column(
        "amie_packets",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "amie_packets",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        op.f("ix_amie_packets_processing_status"),
        "amie_packets",
        ["processing_status"],
        unique=False,
    )
    op.execute(
        "UPDATE amie_packets "
        "SET processing_status = 'processed', "
        "processed_at = COALESCE(packet_timestamp, created_at)"
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(op.f("ix_amie_packets_processing_status"), table_name="amie_packets")
    op.drop_column("amie_packets", "processed_at")
    op.drop_column("amie_packets", "processing_error")
    op.drop_column("amie_packets", "processing_status")
