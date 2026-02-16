from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "Cursed Kurgans"
    ENV: str = "dev"
    API_PREFIX: str = ""

    DATABASE_URL: str

    JWT_SECRET: str
    JWT_ALG: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 30

    CORS_ALLOW_ORIGINS: str = "http://localhost:5173"
    CORS_ALLOW_CREDENTIALS: bool = True

    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WIDGET_BOT_TOKEN: str | None = None  # optionally same
    TELEGRAM_WEBAPP_MAX_AGE_SEC: int = 60 * 60  # 1h

    RATE_LIMIT_AUTH_PER_MIN: int = 20
    RATE_LIMIT_RUN_ACT_PER_MIN: int = 120
    RATE_LIMIT_SHOP_PER_MIN: int = 30

settings = Settings()