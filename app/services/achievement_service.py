from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.achievement import Achievement, UserAchievement
from app.models.wallet import Wallet

def _now():
    return datetime.now(timezone.utc)

def _reward_wallet(wallet: Wallet, reward: dict):
    wallet.chervontsi += int(reward.get("chervontsi", 0))
    wallet.kleidony += int(reward.get("kleidony", 0))

async def ingest_event(session: AsyncSession, user_id, event: str, amount: int = 1, ctx: dict | None = None):
    """
    Called by gameplay endpoints:
      ingest_event(..., "run_complete", 1, {"mode":"quick"})
    This increments progress for matching achievements.
    """
    ctx = ctx or {}
    achs = (await session.execute(select(Achievement).where(Achievement.is_active == True))).scalars().all()

    # naive scan; in prod: index by event+scope in memory cache
    for a in achs:
        cond = a.condition_json
        if cond.get("event") != event:
            continue
        filters = cond.get("filters") or {}
        ok = True
        for k, v in filters.items():
            if ctx.get(k) != v:
                ok = False
                break
        if not ok:
            continue

        ua = await session.get(UserAchievement, {"user_id": user_id, "achievement_id": a.id})
        if not ua:
            ua = UserAchievement(user_id=user_id, achievement_id=a.id, progress=0, claimed_at=None, updated_at=_now())
            session.add(ua)

        if ua.claimed_at is not None:
            continue

        ua.progress += amount
        ua.updated_at = _now()

async def claim_achievement(session: AsyncSession, user_id, achievement_id: str) -> dict:
    a = await session.get(Achievement, achievement_id)
    if not a or not a.is_active:
        raise ValueError("Not found")

    ua = await session.get(UserAchievement, {"user_id": user_id, "achievement_id": achievement_id})
    if not ua:
        raise ValueError("No progress")

    if ua.claimed_at is not None:
        raise ValueError("Already claimed")

    target = int(a.condition_json.get("target", 1))
    if ua.progress < target:
        raise ValueError("Not completed")

    ua.claimed_at = _now()

    w = await session.get(Wallet, user_id)
    if not w:
        w = Wallet(user_id=user_id, chervontsi=0, kleidony=0)
        session.add(w)

    reward = a.reward_json or {}
    _reward_wallet(w, reward)

    return {"achievement_id": a.id, "reward": reward}