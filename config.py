"""
Configuration for Cursed Mounds backend.
All settings via environment variables with sensible defaults.
"""
from functools import lru_cache
from typing import List, Optional, Annotated

from pydantic import Field, validator
from pydantic_settings import BaseSettings, NoDecode


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
    MAX_TAPS_PER_SECOND: float = 10.0  # Physically impossible to tap faster
    MIN_TAP_INTERVAL_MS: int = 50  # Minimum between taps
    SUSPICIOUS_PATTERN_THRESHOLD: int = 50  # Perfect rhythm detection

    # WebSocket
    # IMPORTANT: NoDecode prevents pydantic-settings from trying json.loads() on env strings.
    WEBSOCKET_CORS_ALLOWED_ORIGINS: Annotated[List[str], NoDecode] = ["*"]

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
        """
        Many hosting platforms provide DATABASE_URL like 'postgres://...' or 'postgresql://...'
        which defaults to the synchronous psycopg2 driver. We force an async driver for SQLAlchemy asyncio.
        """
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

    @validator("WEBSOCKET_CORS_ALLOWED_ORIGINS", pre=True)
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            # allow "*" or comma-separated origins
            parts = [origin.strip() for origin in v.split(",") if origin.strip()]
            return parts if parts else ["*"]
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
