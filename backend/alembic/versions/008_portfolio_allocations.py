"""
008 — portfolio_allocations table

사용자가 설정한 자산 배분 목표 비중을 저장합니다.
예: BTC 50%, ETH 30%, SOL 20%

Revision ID: 008_portfolio_allocations
Revises: 007_ml_models
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008_portfolio_allocations"
down_revision = "007_ml_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_allocations",
        sa.Column("symbol", sa.String(20), primary_key=True),
        sa.Column("target_pct", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("portfolio_allocations")
