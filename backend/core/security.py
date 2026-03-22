"""
Security utilities — password hashing and JWT token management.

패스워드: bcrypt 해싱 (passlib)
JWT: HS256 서명, access token 만료 30분 (설정 가능)
API 키 암호화: Fernet 대칭 암호화 (cryptography)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(subject: str | Any) -> str:
    """
    JWT access token 생성.
    subject: 보통 user.id (str(uuid))
    """
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    """
    JWT 검증 후 subject(user_id) 반환.
    유효하지 않으면 None 반환.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload.get("sub")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# API 키 암호화 (Fernet)
# ---------------------------------------------------------------------------

def _get_fernet():
    """SECRET_KEY_ENCRYPTION_KEY 를 32바이트 Fernet 키로 변환."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet

    raw = settings.SECRET_KEY_ENCRYPTION_KEY.encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_api_key(plain: str) -> str:
    """API 키를 암호화해 Base64 문자열로 반환."""
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    """암호화된 API 키를 복호화해 원문 반환."""
    return _get_fernet().decrypt(encrypted.encode()).decode()
