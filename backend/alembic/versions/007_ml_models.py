"""
007 — ml_models table

LSTM 모델 학습 결과를 저장합니다.
- model_data : base64-encoded PyTorch state_dict (< ~300KB)
- scaler_data : JSON — 정규화 파라미터 (close_min/range, vol_min/range)

Revision ID: 007_ml_models
Revises: 006_optimization_results
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "007_ml_models"
down_revision = "006_optimization_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ml_models",
        sa.Column("task_id", sa.String(64), primary_key=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("interval", sa.String(5), nullable=False),
        sa.Column("start_date", sa.String(32), nullable=False),
        sa.Column("end_date", sa.String(32), nullable=False),
        sa.Column("seq_len", sa.Integer, nullable=False, server_default="60"),
        sa.Column("hidden_size", sa.Integer, nullable=False, server_default="64"),
        sa.Column("num_layers", sa.Integer, nullable=False, server_default="2"),
        sa.Column("epochs_trained", sa.Integer, nullable=True),
        sa.Column("n_train_samples", sa.Integer, nullable=True),
        sa.Column("val_loss", sa.Float, nullable=True),
        sa.Column("model_data", sa.Text, nullable=True),    # base64 weights
        sa.Column("scaler_data", sa.Text, nullable=True),   # JSON
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_ml_models_symbol", "ml_models", ["symbol"])
    op.create_index("ix_ml_models_created", "ml_models", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ml_models_created", "ml_models")
    op.drop_index("ix_ml_models_symbol", "ml_models")
    op.drop_table("ml_models")
