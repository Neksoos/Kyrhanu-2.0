from __future__ import annotations

import os
import secrets

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Cursed Kurgans"
    ENV: str = "dev"  # dev | prod
    API_PREFIX: str = ""

    # Example: postgresql+asyncpg://user:pass@host:5432/dbname
    DATABASE_URL: str

    # Auth
    JWT_SECRET: str = ""  # if empty in dev -> auto-generate
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 30

    # CORS
    # comma-separated
    # Railway variables used in this project screenshots: CORS_ORIGINS / FRONTEND_ORIGIN
    CORS_ALLOW_ORIGINS: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("CORS_ALLOW_ORIGINS", "CORS_ORIGINS", "CORS_ORIGIN"),
    )
    CORS_ALLOW_CREDENTIALS: bool = True

    # Telegram
    # Railway variable used in this project screenshots: TG_BOT_TOKEN
    TELEGRAM_BOT_TOKEN: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "TG_BOT_TOKEN"),
    )
    TELEGRAM_WIDGET_BOT_TOKEN: str | None = None
    TELEGRAM_WEBAPP_MAX_AGE_SEC: int = 60 * 60  # 1h

    # Rate limits
    RATE_LIMIT_AUTH_PER_MIN: int = 20
    RATE_LIMIT_RUN_ACT_PER_MIN: int = 120
    RATE_LIMIT_SHOP_PER_MIN: int = 30

    def validate_runtime(self) -> None:
        # DATABASE_URL must always exist
        if not self.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is required")

        # In prod: require secrets/tokens explicitly
        if self.ENV.lower() in ("prod", "production"):
            if not self.JWT_SECRET or len(self.JWT_SECRET) < 32:
                raise RuntimeError("JWT_SECRET is required in production (>=32 chars)")
            if not self.TELEGRAM_BOT_TOKEN:
                raise RuntimeError("TELEGRAM_BOT_TOKEN is required in production")
        else:
            # Dev convenience
            if not self.JWT_SECRET or len(self.JWT_SECRET) < 32:
                self.JWT_SECRET = secrets.token_hex(48)
                print("[env] JWT_SECRET missing/weak -> generated dev secret. Set JWT_SECRET for stable tokens.")
            if not self.TELEGRAM_BOT_TOKEN:
                print("[env] TELEGRAM_BOT_TOKEN is empty (dev). Telegram login will not work until you set it.")

        # If Railway provides FRONTEND_ORIGIN but not CORS_ALLOW_ORIGINS, honor it.
        # Keeps compatibility with older variable naming used in deployment screenshots.
        frontend_origin = os.getenv("FRONTEND_ORIGIN")
        if frontend_origin and self.CORS_ALLOW_ORIGINS == "http://localhost:5173":
            self.CORS_ALLOW_ORIGINS = frontend_origin


settings = Settings()
settings.validate_runtime()