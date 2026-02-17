# app/core/db.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def _normalize_db_url(url: str) -> str:
    """
    Railway часто дає DATABASE_URL як:
      postgres://user:pass@host:port/db
    або:
      postgresql://...
    Для async SQLAlchemy нам треба:
      postgresql+asyncpg://...
    """
    if not url:
        return url

    # already async
    if "postgresql+asyncpg://" in url:
        return url

    # railway legacy scheme
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]

    # plain postgresql -> add driver if missing
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return "postgresql+asyncpg://" + url[len("postgresql://") :]

    return url


DATABASE_URL = _normalize_db_url(settings.DATABASE_URL)

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass