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
    # Exchange Selection
    # -------------------------------------------------------------------------
    ACTIVE_EXCHANGE: str = "binance"   # "binance" | "upbit"

    # -------------------------------------------------------------------------
    # Binance Exchange
    # Keys are optional - public endpoints work without authentication
    # -------------------------------------------------------------------------
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET_KEY: str = ""
    BINANCE_TESTNET: bool = False

    # -------------------------------------------------------------------------
    # Upbit Exchange (Korean crypto exchange — KRW markets)
    # Keys are required for order placement; market data works without keys
    # -------------------------------------------------------------------------
    UPBIT_ACCESS_KEY: str = ""
    UPBIT_SECRET_KEY: str = ""

    # -------------------------------------------------------------------------
    # JWT Security
    # -------------------------------------------------------------------------
    JWT_SECRET_KEY: str = "change-me-generate-a-strong-secret-key-here"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # -------------------------------------------------------------------------
    # API Key Encryption (Phase 7)
    # Used to AES-encrypt user exchange API keys stored in DB
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    # -------------------------------------------------------------------------
    SECRET_KEY_ENCRYPTION_KEY: str = "change-me-generate-a-strong-encryption-key"

    # -------------------------------------------------------------------------
    # Trading Safety
    # -------------------------------------------------------------------------
    LIVE_TRADING_ENABLED: bool = False
    PAPER_TRADING_MODE: bool = True

    # -------------------------------------------------------------------------
    # Sentiment / News
    # -------------------------------------------------------------------------
    NEWSAPI_KEY: str = ""          # Optional — CryptoPanic RSS works without it
    OPENAI_API_KEY: str = ""       # Optional — for future GPT enhancement
    PAPER_INITIAL_BALANCE: float = 10000.0   # USD starting balance for paper trading

    # -------------------------------------------------------------------------
    # Risk Management
    # -------------------------------------------------------------------------
    RISK_MAX_POSITION_PCT: float = 0.02       # 2% of portfolio per trade
    RISK_DAILY_LOSS_LIMIT_PCT: float = 0.05   # halt if daily drawdown > 5%
    RISK_MAX_OPEN_POSITIONS: int = 3

    # -------------------------------------------------------------------------
    # Telegram Notifications (Phase 6)
    # Bot token: https://t.me/BotFather → /newbot
    # Chat ID: send a message to your bot, then:
    #   curl https://api.telegram.org/bot<TOKEN>/getUpdates
    # -------------------------------------------------------------------------
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.TELEGRAM_BOT_TOKEN and self.TELEGRAM_CHAT_ID)

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

    @property
    def has_upbit_credentials(self) -> bool:
        return bool(self.UPBIT_ACCESS_KEY and self.UPBIT_SECRET_KEY)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance - called once per process."""
    return Settings()


settings = get_settings()
