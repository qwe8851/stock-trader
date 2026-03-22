"""
006 — optimization_results table

전략 파라미터 최적화 결과를 저장합니다.
- Optuna study 결과 (best params, all trial summaries)
- objective_metric: sharpe | return | drawdown

Revision ID: 006_optimization_results
Revises: 005_user_api_keys
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006_optimization_results"
down_revision = "005_user_api_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_results",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("strategy", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("interval", sa.String(5), nullable=False),
        sa.Column("start_date", sa.String(32), nullable=False),
        sa.Column("end_date", sa.String(32), nullable=False),
        sa.Column("n_trials", sa.Integer, nullable=False),
        sa.Column("objective_metric", sa.String(20), nullable=False, server_default="sharpe"),
        sa.Column("best_params", sa.Text, nullable=True),       # JSON
        sa.Column("best_value", sa.Float, nullable=True),
        sa.Column("best_return_pct", sa.Float, nullable=True),
        sa.Column("best_sharpe", sa.Float, nullable=True),
        sa.Column("best_drawdown_pct", sa.Float, nullable=True),
        sa.Column("best_win_rate_pct", sa.Float, nullable=True),
        sa.Column("best_trades", sa.Integer, nullable=True),
        sa.Column("trials_summary", sa.Text, nullable=True),    # JSON — top-N trial summaries
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_opt_results_strategy", "optimization_results", ["strategy"])
    op.create_index("ix_opt_results_created", "optimization_results", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_opt_results_created", "optimization_results")
    op.drop_index("ix_opt_results_strategy", "optimization_results")
    op.drop_table("optimization_results")
