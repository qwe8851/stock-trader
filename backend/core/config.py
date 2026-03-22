"""
Application configuration using Pydantic Settings.
Values are loaded from environment variables (or .env file).
"""
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # -------------------------------------------------------------------------
    # Database
    # -------------------------------------------------------------------------
    DATABASE_URL: str = (
        "postgresql+asyncpg://trader:traderpassword@localhost:5432/stocktrader"
    )

    # -------------------------------------------------------------------------
    # Redis
    # -------------------------------------------------------------------------
    REDIS_URL: str = "redis://localhost:6379/0"

    # -------------------------------------------------------------------------
    # Binance Exchange
    # Keys are optional - public endpoints work without authentication
    # -------------------------------------------------------------------------
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET_KEY: str = ""
    BINANCE_TESTNET: bool = False

    # -------------------------------------------------------------------------
    # JWT Security
    # -------------------------------------------------------------------------
    JWT_SECRET_KEY: str = "change-me-generate-a-strong-secret-key-here"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # -------------------------------------------------------------------------
    # Trading Safety
    # -------------------------------------------------------------------------
    LIVE_TRADING_ENABLED: bool = False
    PAPER_TRADING_MODE: bool = True

    # -------------------------------------------------------------------------
    # CORS
    # -------------------------------------------------------------------------
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except ValueError:
                # Fallback: comma-separated string
                return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def has_binance_credentials(self) -> bool:
        """True when API key and secret are both provided."""
        return bool(self.BINANCE_API_KEY and self.BINANCE_SECRET_KEY)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance - called once per process."""
    return Settings()


settings = get_settings()
