from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user_id
from app.services.daily_service import roll_variants, select_and_claim

router = APIRouter(prefix="/daily", tags=["daily"])

@router.post("/claim")
async def daily_claim(
    body: dict,  # expects { "variant": "A"|"B"|"C" } (можна додатково)
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    variant = (body or {}).get("variant", "A")
    try:
        today = await select_and_claim(db, user_id, date.today(), variant)
        await db.commit()
        return {"ok": True, "today": today}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))