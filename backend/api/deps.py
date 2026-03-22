"""
FastAPI dependency injection — 인증된 유저를 라우터에 주입합니다.

사용 예:
    @router.get("/me")
    async def me(user: User = Depends(get_current_user)):
        return user

    @router.get("/admin")
    async def admin(user: User = Depends(get_current_superuser)):
        ...
"""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from core.security import decode_access_token
from db.models.user import User
from db.session import AsyncSessionLocal

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    """
    Authorization: Bearer <token> 헤더에서 JWT를 추출해 유저를 반환.
    유효하지 않으면 401을 반환합니다.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(User).where(User.id == uuid.UUID(user_id))
        )
        user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return user


async def get_current_superuser(
    user: User = Depends(get_current_user),
) -> User:
    """슈퍼유저만 접근 가능한 엔드포인트에 사용."""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return user
