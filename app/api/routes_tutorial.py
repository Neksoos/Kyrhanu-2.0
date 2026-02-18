from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user_id

router = APIRouter(prefix="/tutorial", tags=["tutorial"])


@router.get("")
async def tutorial_get(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    row = (
        await db.execute(
            text(
                """
                SELECT step, completed, flags, rewards_claimed
                FROM tutorial_state
                WHERE user_id = :uid
                """
            ),
            {"uid": user_id},
        )
    ).mappings().first()

    if not row:
        return {"ok": True, "step": 1, "completed": False, "flags": {}, "rewards_claimed": {}}

    return {"ok": True, **dict(row)}
