"""Initial schema - users table and OHLCV hypertable

Revision ID: 001
Revises:
Create Date: 2026-03-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # Enable TimescaleDB extension
    # -------------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # -------------------------------------------------------------------------
    # users table
    # -------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default="false"),
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
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # -------------------------------------------------------------------------
    # ohlcv table (becomes a hypertable below)
    # -------------------------------------------------------------------------
    op.create_table(
        "ohlcv",
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("interval", sa.String(5), nullable=False),
        sa.Column("open", sa.Numeric(24, 8), nullable=False),
        sa.Column("high", sa.Numeric(24, 8), nullable=False),
        sa.Column("low", sa.Numeric(24, 8), nullable=False),
        sa.Column("close", sa.Numeric(24, 8), nullable=False),
        sa.Column("volume", sa.Numeric(36, 8), nullable=False),
        sa.Column(
            "quote_volume",
            sa.Numeric(36, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column("num_trades", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("time", "symbol", "interval"),
    )

    # Composite indexes for common query patterns
    op.create_index("ix_ohlcv_symbol_time", "ohlcv", ["symbol", "time"])
    op.create_index(
        "ix_ohlcv_symbol_interval_time", "ohlcv", ["symbol", "interval", "time"]
    )

    # Convert the ohlcv table into a TimescaleDB hypertable partitioned by time.
    # if_not_exists=TRUE prevents errors on re-runs (e.g. in dev environments).
    op.execute(
        """
        SELECT create_hypertable(
            'ohlcv',
            'time',
            if_not_exists => TRUE,
            migrate_data   => TRUE
        )
        """
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order.
    # Note: dropping a hypertable also removes all its chunks.
    op.drop_table("ohlcv")
    op.drop_table("users")
    # We intentionally leave timescaledb extension in place to avoid
    # accidental data loss in shared environments.
