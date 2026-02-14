"""
Configuration for Cursed Mounds backend.
All settings via environment variables with sensible defaults.
"""
from functools import lru_cache
from typing import List, Optional
import json

from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://kurgan_user:kurgan_secret_2024@localhost:5432/cursed_mounds"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Security
    SECRET_KEY: str = Field(default="dev-secret-key-must-be-32-chars-long!")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Environment
    ENVIRONMENT: str = "development"  # development, staging, production
    DEBUG: bool = False

    # Anti-cheat
    ANTI_CHEAT_ENABLED: bool = True
    MAX_TAPS_PER_SECOND: float = 10.0
    MIN_TAP_INTERVAL_MS: int = 50
    SUSPICIOUS_PATTERN_THRESHOLD: int = 50

    # WebSocket CORS
    # IMPORTANT: keep as str so pydantic-settings won't json.loads() it and crash.
    # We read env var WEBSOCKET_CORS_ALLOWED_ORIGINS into this raw string.
    WEBSOCKET_CORS_ALLOWED_ORIGINS_RAW: str = Field(
        default="*",
        validation_alias="WEBSOCKET_CORS_ALLOWED_ORIGINS",
    )

    # LiveOps
    EVENT_CONFIG_PATH: str = "config/events.yaml"

    # Monetization
    DEFAULT_CURRENCY_PACKS: dict = {
        "starter": {"kleynodu": 100, "price_usd": 0.99, "bonus_chervontsi": 500},
        "warrior": {"kleynodu": 550, "price_usd": 4.99, "bonus_chervontsi": 3000},
        "hetman": {"kleynodu": 1200, "price_usd": 9.99, "bonus_chervontsi": 7000},
        "kozak": {"kleynodu": 2500, "price_usd": 19.99, "bonus_chervontsi": 15000},
    }

    # Ads
    REWARDED_AD_COOLDOWN_MINUTES: int = 5
    MAX_ADS_PER_DAY: int = 10
    AD_REWARD_KLEYNODU: int = 5
    AD_REWARD_CHERVONTSI: int = 100

    @validator("DATABASE_URL", pre=True)
    def normalize_database_url(cls, v):
        if not isinstance(v, str):
            return v
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        if v.startswith("postgresql+psycopg2://"):
            return "postgresql+asyncpg://" + v[len("postgresql+psycopg2://"):]
        if v.startswith("postgresql+psycopg://"):
            return "postgresql+asyncpg://" + v[len("postgresql+psycopg://"):]
        return v

    @validator("SECRET_KEY")
    def validate_secret_key(cls, v):
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @property
    def WEBSOCKET_CORS_ALLOWED_ORIGINS(self) -> List[str]:
        """
        Accept env formats:
          - "*" 
          - "https://a.com"
          - "https://a.com,https://b.com"
          - '["https://a.com","https://b.com"]' (JSON list)
          - "" (empty) -> ["*"]
        """
        s = (self.WEBSOCKET_CORS_ALLOWED_ORIGINS_RAW or "").strip()
        if not s:
            return ["*"]
        if s == "*":
            return ["*"]
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    out = [str(x).strip() for x in parsed if str(x).strip()]
                    return out if out else ["*"]
            except Exception:
                pass
        parts = [p.strip() for p in s.split(",") if p.strip()]
        return parts if parts else ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()