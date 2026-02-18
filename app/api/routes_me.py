from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user_id
from app.models.user import User
from app.models.wallet import Wallet

router = APIRouter(tags=["me"])


@router.get("/me")
async def me(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    u = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    w = await db.get(Wallet, user_id)
    return {
        "ok": True,
        "user": {
            "id": str(u.id) if u else str(user_id),
            "email": getattr(u, "email", None),
            "telegram_id": getattr(u, "telegram_id", None),
            "telegram_username": getattr(u, "telegram_username", None),
        },
        "wallet": {
            "chervontsi": int(getattr(w, "chervontsi", 0) or 0),
            "kleidony": int(getattr(w, "kleidony", 0) or 0),
        },
    }
