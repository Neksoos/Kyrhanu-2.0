import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.db import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))