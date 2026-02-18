from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.api.deps import get_db, get_current_user_id
from app.services.achievement_service import claim_achievement

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get("")
async def achievements_list(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    # Minimal list: merges content + user state. Front can render simple cards.
    rows = (await db.execute(
        text(
            """
            SELECT a.id, a.name, a.category, a.rarity, a.hidden,
                   COALESCE(ua.progress, 0) AS progress,
                   (ua.claimed_at IS NOT NULL) AS claimed
            FROM achievements a
            LEFT JOIN user_achievements ua
              ON ua.achievement_id = a.id AND ua.user_id = :uid
            WHERE a.is_active = TRUE
            ORDER BY a.category, a.rarity, a.id
            """
        ),
        {"uid": user_id},
    )).mappings().all()

    return {"ok": True, "achievements": [dict(r) for r in rows]}

@router.post("/claim")
async def achievements_claim(
    body: dict,  # { achievement_id }
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    aid = (body or {}).get("achievement_id")
    if not aid:
        raise HTTPException(status_code=400, detail="Missing achievement_id")
    try:
        res = await claim_achievement(db, user_id, aid)
        await db.commit()
        return {"ok": True, **res}
    except ValueError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/share-card")
async def achievements_share_card(user_id: str = Depends(get_current_user_id)):
    # у проді: генеруємо signed payload для фронта або віддаємо URL з CDN
    return {"card_payload": {"type":"achievement_card","user":"<id>","sig":"<signed>"}}