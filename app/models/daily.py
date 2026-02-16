import uuid
from datetime import date, datetime
from sqlalchemy import Date, DateTime, ForeignKey, String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class DailyRoll(Base):
    __tablename__ = "daily_rolls"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day_key: Mapped[date] = mapped_column(Date, primary_key=True)
    selected_variant: Mapped[str] = mapped_column(String(1), default="A")  # A/B/C
    roll_json: Mapped[dict] = mapped_column(JSON)  # hero+loadout+story
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pity_epic: Mapped[int] = mapped_column(Integer, default=0)
    pity_legendary: Mapped[int] = mapped_column(Integer, default=0)