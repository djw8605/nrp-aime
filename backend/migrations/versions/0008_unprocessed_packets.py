"""Add table for unprocessed packet visibility.

Revision ID: 0008_unprocessed_packets
Revises: 0007_store_transaction_ids
Create Date: 2026-03-14 23:10:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0008_unprocessed_packets"
down_revision = "0007_store_transaction_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply schema changes."""
    op.create_table(
        "amie_unprocessed_packets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("packet_fingerprint", sa.String(), nullable=False),
        sa.Column("packet_rec_id", sa.BigInteger(), nullable=True),
        sa.Column("trans_rec_id", sa.BigInteger(), nullable=True),
        sa.Column("transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("packet_type", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("raw_packet", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("packet_fingerprint"),
    )
    op.create_index(
        op.f("ix_amie_unprocessed_packets_packet_fingerprint"),
        "amie_unprocessed_packets",
        ["packet_fingerprint"],
        unique=True,
    )
    op.create_index(
        op.f("ix_amie_unprocessed_packets_packet_rec_id"),
        "amie_unprocessed_packets",
        ["packet_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_unprocessed_packets_trans_rec_id"),
        "amie_unprocessed_packets",
        ["trans_rec_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_unprocessed_packets_transaction_id"),
        "amie_unprocessed_packets",
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_unprocessed_packets_packet_type"),
        "amie_unprocessed_packets",
        ["packet_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_amie_unprocessed_packets_failure_reason"),
        "amie_unprocessed_packets",
        ["failure_reason"],
        unique=False,
    )


def downgrade() -> None:
    """Rollback schema changes."""
    op.drop_index(
        op.f("ix_amie_unprocessed_packets_failure_reason"),
        table_name="amie_unprocessed_packets",
    )
    op.drop_index(
        op.f("ix_amie_unprocessed_packets_packet_type"),
        table_name="amie_unprocessed_packets",
    )
    op.drop_index(
        op.f("ix_amie_unprocessed_packets_transaction_id"),
        table_name="amie_unprocessed_packets",
    )
    op.drop_index(
        op.f("ix_amie_unprocessed_packets_trans_rec_id"),
        table_name="amie_unprocessed_packets",
    )
    op.drop_index(
        op.f("ix_amie_unprocessed_packets_packet_rec_id"),
        table_name="amie_unprocessed_packets",
    )
    op.drop_index(
        op.f("ix_amie_unprocessed_packets_packet_fingerprint"),
        table_name="amie_unprocessed_packets",
    )
    op.drop_table("amie_unprocessed_packets")
