"""
004 — portfolio_snapshots table

포트폴리오 가치 이력을 저장합니다.
Celery Beat가 1시간마다 스냅샷을 기록하며, 프론트엔드 P&L 차트에 활용됩니다.

Revision ID: 004_portfolio_snapshots
Revises: 003_live_orders
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_portfolio_snapshots"
down_revision = "003_live_orders"   # 003 revision ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "snapshot_time",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("total_value_usd", sa.Float, nullable=False),
        sa.Column("available_usd", sa.Float, nullable=False),
        sa.Column("open_positions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("exchange", sa.String(20), nullable=False, server_default="binance"),
        sa.Column("mode", sa.String(10), nullable=False, server_default="PAPER"),
    )
    op.create_index(
        "ix_portfolio_snapshots_time",
        "portfolio_snapshots",
        ["snapshot_time"],
    )


def downgrade() -> None:
    op.drop_index("ix_portfolio_snapshots_time", "portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
