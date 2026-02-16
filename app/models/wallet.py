import uuid
from sqlalchemy import BigInteger, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class Wallet(Base):
    __tablename__ = "wallet"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    chervontsi: Mapped[int] = mapped_column(BigInteger, default=0)
    kleidony: Mapped[int] = mapped_column(BigInteger, default=0)