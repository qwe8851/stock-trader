"""
Auth endpoints.

POST /api/auth/register  — 회원가입
POST /api/auth/login     — 로그인 (JWT 발급)
GET  /api/auth/me        — 현재 유저 정보
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select

from api.deps import get_current_user
from core.security import create_access_token, hash_password, verify_password
from db.models.user import User
from db.session import AsyncSessionLocal

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: str
    email: str
    is_superuser: bool
    created_at: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest) -> TokenResponse:
    """
    새 계정을 생성하고 JWT 토큰을 반환합니다.
    최초 가입자는 자동으로 슈퍼유저가 됩니다.
    """
    async with AsyncSessionLocal() as session:
        # 이메일 중복 확인
        existing = await session.execute(
            select(User).where(User.email == body.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        # 첫 번째 유저는 슈퍼유저
        count_result = await session.execute(select(User))
        is_first = len(count_result.scalars().all()) == 0

        user = User(
            id=uuid.uuid4(),
            email=body.email,
            hashed_password=hash_password(body.password),
            is_active=True,
            is_superuser=is_first,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        user=_user_dict(user),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest) -> TokenResponse:
    """이메일/패스워드로 로그인 후 JWT 토큰을 반환합니다."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.email == body.email)
        )
        user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        user=_user_dict(user),
    )


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    """현재 로그인된 유저 정보를 반환합니다."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        is_superuser=user.is_superuser,
        created_at=user.created_at.isoformat(),
    )


def _user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "is_superuser": user.is_superuser,
    }
