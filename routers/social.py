"""
Social features: referrals, sharing, leaderboards.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models import User
from services.analytics import analytics, TrackedEvent
from redis_client import leaderboard_get_range, leaderboard_get_rank, leaderboard_add
from routers.auth import get_current_user

router = APIRouter()


@router.post("/referral/claim")
async def claim_referral(
    referral_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Use a referral code."""
    if current_user.referred_by:
        raise HTTPException(status_code=400, detail="Already used referral")
    
    # Find referrer
    result = await db.execute(
        select(User).where(User.referral_code == referral_code)
    )
    referrer = result.scalar_one_or_none()
    
    if not referrer:
        raise HTTPException(status_code=404, detail="Invalid code")
    
    if referrer.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot refer yourself")
    
    # Apply
    current_user.referred_by = referrer.id
    current_user.kleynodu += 100  # Bonus for new user
    referrer.kleynodu += 50  # Bonus for referrer
    
    await db.commit()
    
    # Track
    await analytics.track(TrackedEvent(
        name="referral_used",
        user_id=current_user.id,
        session_id=None,
        properties={"referrer_id": referrer.id}
    ))
    
    return {
        "success": True,
        "bonus_kleynodu": 100,
        "referrer": referrer.username
    }


@router.get("/leaderboard/global")
async def get_global_leaderboard(
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """Get global glory leaderboard."""
    # Update Redis with fresh data (in production: background job)
    top = await leaderboard_get_range("global:glory", 0, limit - 1)
    
    # Enrich with user data
    result = []
    for rank, (user_id, glory) in enumerate(top, 1):
        # Get user info from cache or DB
        user_data = await cache_get(f"user:{user_id}:public") or {
            "username": f"Player_{user_id}",
            "level": 1
        }
        
        entry = {
            "rank": rank,
            "user_id": int(user_id),
            "username": user_data.get("username"),
            "glory": int(glory),
            "level": user_data.get("level", 1),
            "is_me": int(user_id) == current_user.id
        }
        result.append(entry)
    
    # Get user's rank if not in top
    user_rank = None
    if not any(e["is_me"] for e in result):
        user_rank = await leaderboard_get_rank(str(current_user.id), "global:glory")
    
    return {
        "leaderboard": result,
        "my_rank": user_rank + 1 if user_rank is not None else None,
        "my_glory": current_user.glory
    }


@router.post("/share")
async def generate_share(
    share_type: str,  # daily, achievement, boss, referral
    current_user: User = Depends(get_current_user)
):
    """Generate shareable content."""
    if share_type == "referral":
        text = f"Приєднуйся до Проклятих Курганів! Мій код: {current_user.referral_code}"
        url = f"https://t.me/CursedMoundsBot?start={current_user.referral_code}"
    elif share_type == "daily":
        text = f"Сьогодні я — {current_user.display_name or 'козак'} з {current_user.glory} слави! А ти?"
        url = "https://t.me/CursedMoundsBot"
    else:
        text = "Граю в Прокляті Кургани — етно-українська гра про міфологію!"
        url = "https://t.me/CursedMoundsBot"
    
    return {
        "text": text,
        "url": url,
        "telegram_share_url": f"https://t.me/share/url?url={url}&text={text}"
    }