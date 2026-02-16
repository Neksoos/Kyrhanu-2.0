import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class Achievement(Base):
    __tablename__ = "achievements"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # "A0001"
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(32))
    rarity: Mapped[str] = mapped_column(String(16))
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    condition_json: Mapped[dict] = mapped_column(JSON)
    reward_json: Mapped[dict] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class UserAchievement(Base):
    __tablename__ = "user_achievements"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    achievement_id: Mapped[str] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"), primary_key=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))