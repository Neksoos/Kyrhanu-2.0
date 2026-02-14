"""
Database configuration with SQLAlchemy async.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from config import settings

# Create async engine
# (DATABASE_URL is normalized in config.py, but we keep a local var for clarity.)
db_url = settings.DATABASE_URL
engine = create_async_engine(
    db_url,
    echo=settings.DEBUG,
    future=True,
    poolclass=NullPool if settings.ENVIRONMENT == "testing" else None,
)

# Session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncSession:
    """Dependency for getting database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        # Tables created via migrations, verify connection
        from sqlalchemy import text
        await conn.execute(text("SELECT 1"))


async def close_db():
    """Close database connections."""
    await engine.dispose()