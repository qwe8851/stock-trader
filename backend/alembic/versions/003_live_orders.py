"""
003 — live_orders table

Stores all executed orders (both paper and live) for audit and reporting.
In-memory paper orders are still used during a session; this table is written
on every order execution so they survive restarts.

Revision ID: 003_live_orders
Revises: 002_backtest_results
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_live_orders"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_orders",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("side", sa.String(10), nullable=False),       # BUY | SELL
        sa.Column("quantity", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=False),
        sa.Column("size_usd", sa.Float, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),     # FILLED | PENDING | FAILED
        sa.Column("mode", sa.String(10), nullable=False),       # PAPER | LIVE
        sa.Column("exchange", sa.String(20), nullable=False, server_default="binance"),
        sa.Column("strategy", sa.String(50), nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("raw_response", sa.Text, nullable=True),      # JSON from exchange
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_live_orders_symbol", "live_orders", ["symbol"])
    op.create_index("ix_live_orders_created_at", "live_orders", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_live_orders_created_at", "live_orders")
    op.drop_index("ix_live_orders_symbol", "live_orders")
    op.drop_table("live_orders")
