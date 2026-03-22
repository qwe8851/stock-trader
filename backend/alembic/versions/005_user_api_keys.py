"""
005 — user_api_keys table

유저별 거래소 API 키를 암호화해 저장합니다.
- access_key, secret_key 는 Fernet 대칭 암호화 후 저장
- 복호화는 backend 전용 (SECRET_KEY_ENCRYPTION_KEY 필요)

Revision ID: 005_user_api_keys
Revises: 004_portfolio_snapshots
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005_user_api_keys"
down_revision = "004_portfolio_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(20), nullable=False),   # binance | upbit
        sa.Column("access_key_enc", sa.Text, nullable=False),   # Fernet encrypted
        sa.Column("secret_key_enc", sa.Text, nullable=False),   # Fernet encrypted
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("user_id", "exchange", name="uq_user_exchange"),
    )
    op.create_index("ix_user_api_keys_user_id", "user_api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_api_keys_user_id", "user_api_keys")
    op.drop_table("user_api_keys")
