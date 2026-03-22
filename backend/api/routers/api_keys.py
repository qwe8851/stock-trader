"""
User API key management.

GET    /api/keys          — 저장된 거래소 키 목록 (복호화 없이 마스킹)
POST   /api/keys          — 거래소 API 키 저장/업데이트 (암호화 저장)
DELETE /api/keys/{exchange} — 특정 거래소 키 삭제
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select

from api.deps import get_current_user
from core.security import decrypt_api_key, encrypt_api_key
from db.models.user import User
from db.session import AsyncSessionLocal

router = APIRouter(prefix="/api/keys", tags=["api-keys"])


# ---------------------------------------------------------------------------
# Inline SQLAlchemy model (no separate file to keep things lean)
# ---------------------------------------------------------------------------

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from db.session import Base


class UserApiKey(Base):
    __tablename__ = "user_api_keys"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    exchange: Mapped[str] = mapped_column(sa.String(20), nullable=False)
    access_key_enc: Mapped[str] = mapped_column(sa.Text, nullable=False)
    secret_key_enc: Mapped[str] = mapped_column(sa.Text, nullable=False)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ApiKeyRequest(BaseModel):
    exchange: str       # "binance" | "upbit"
    access_key: str
    secret_key: str


class ApiKeyInfo(BaseModel):
    exchange: str
    access_key_preview: str   # 앞 4자 + ****


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ApiKeyInfo])
async def list_keys(user: User = Depends(get_current_user)) -> list[ApiKeyInfo]:
    """저장된 API 키 목록 (마스킹)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserApiKey).where(UserApiKey.user_id == user.id)
        )
        rows = result.scalars().all()

    return [
        ApiKeyInfo(
            exchange=r.exchange,
            access_key_preview=_mask(decrypt_api_key(r.access_key_enc)),
        )
        for r in rows
    ]


@router.post("", status_code=201)
async def save_key(
    body: ApiKeyRequest,
    user: User = Depends(get_current_user),
) -> dict:
    """거래소 API 키를 암호화해 저장합니다. 기존 키가 있으면 덮어씁니다."""
    exchange = body.exchange.lower()
    if exchange not in ("binance", "upbit"):
        raise HTTPException(400, "exchange must be 'binance' or 'upbit'")

    enc_access = encrypt_api_key(body.access_key)
    enc_secret = encrypt_api_key(body.secret_key)

    async with AsyncSessionLocal() as session:
        # 기존 키 확인
        result = await session.execute(
            select(UserApiKey).where(
                UserApiKey.user_id == user.id,
                UserApiKey.exchange == exchange,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.access_key_enc = enc_access
            existing.secret_key_enc = enc_secret
        else:
            session.add(UserApiKey(
                id=uuid.uuid4(),
                user_id=user.id,
                exchange=exchange,
                access_key_enc=enc_access,
                secret_key_enc=enc_secret,
            ))
        await session.commit()

    return {"exchange": exchange, "saved": True}


@router.delete("/{exchange}", status_code=204)
async def delete_key(
    exchange: str,
    user: User = Depends(get_current_user),
) -> None:
    """특정 거래소의 API 키를 삭제합니다."""
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(UserApiKey).where(
                UserApiKey.user_id == user.id,
                UserApiKey.exchange == exchange.lower(),
            )
        )
        await session.commit()


def _mask(key: str) -> str:
    """앞 4자리만 보여주고 나머지는 *로 마스킹."""
    if len(key) <= 4:
        return "****"
    return key[:4] + "*" * (len(key) - 4)
