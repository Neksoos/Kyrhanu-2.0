"""
Live boss battle system.
Real-time collaborative boss fights with WebSocket updates.
"""
import random

from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from datetime import datetime, timedelta

from database import get_db
from models import User, LiveBoss, BossAttack
from services.analytics import analytics, TrackedEvent
from services.live_ops import live_ops
from routers.auth import get_current_user
from redis_client import get_redis, publish_event, cache_get, cache_set

router = APIRouter()


class BossAttackRequest(BaseModel):
    boss_id: int
    use_kleynodu: int = 0


@router.get("/active")
async def get_active_bosses(
    db: AsyncSession = Depends(get_db)
):
    """Get currently active bosses."""
    now = datetime.utcnow()
    
    result = await db.execute(
        select(LiveBoss).where(
            and_(
                LiveBoss.status.in_(["spawning", "active"]),
                LiveBoss.despawn_at > now
            )
        )
    )
    bosses = result.scalars().all()
    
    # Enhance with live data from Redis
    response = []
    for boss in bosses:
        # Get live health from Redis (more frequent updates than DB)
        live_health = await get_redis().get(f"boss:{boss.id}:health")
        current_health = int(live_health) if live_health else boss.current_health
        
        # Get top attackers from Redis
        top_attackers = await get_redis().zrevrange(
            f"boss:{boss.id}:attackers", 0, 9, withscores=True
        )
        
        response.append({
            "id": boss.id,
            "name": boss.name,
            "description": boss.description,
            "image_url": boss.image_url,
            "total_health": boss.total_health,
            "current_health": current_health,
            "health_percent": (current_health / boss.total_health) * 100,
            "status": boss.status,
            "despawns_at": boss.despawn_at.isoformat(),
            "top_attackers": [
                {"user_id": int(uid), "damage": int(dmg)}
                for uid, dmg in top_attackers
            ],
            "rewards": {
                "chervontsi_pool": boss.reward_chervontsi_pool,
                "kleynodu_pool": boss.reward_kleynodu_pool,
                "special_drops": boss.special_drops
            }
        })
    
    return {"bosses": response}


@router.post("/attack")
async def attack_boss(
    payload: BossAttackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Attack a live boss.
    """
    boss_id = payload.boss_id
    use_kleynodu = payload.use_kleynodu

    boss = await db.get(LiveBoss, boss_id)
    if not boss or boss.status != "active":
        raise HTTPException(status_code=404, detail="Boss not active")
    
    if boss.current_health <= 0:
        raise HTTPException(status_code=400, detail="Boss already defeated")
    
    # Check if user has energy or uses kleynodu
    if use_kleynodu > 0:
        if current_user.kleynodu < use_kleynodu:
            raise HTTPException(status_code=402, detail="Insufficient kleynodu")
        current_user.kleynodu -= use_kleynodu
    else:
        if current_user.energy < 5:
            raise HTTPException(status_code=403, detail="Need 5 energy (or use kleynodu)")
        current_user.energy -= 5
    
    # Calculate damage
    base_damage = random.randint(10, 50)
    
    # Apply multipliers
    multipliers = await live_ops.get_active_multipliers()
    damage = int(base_damage * multipliers.get("boss_damage", 1.0))
    
    # Kleynodu boost
    if use_kleynodu >= 10:
        damage = int(damage * 2.5)  # 2.5x damage for premium
    
    # Update boss health (optimistic, race conditions handled by DB)
    boss.current_health = max(0, boss.current_health - damage)
    
    # Record attack
    attack = BossAttack(
        boss_id=boss_id,
        user_id=current_user.id,
        damage_dealt=damage,
        attack_type="premium" if use_kleynodu > 0 else "normal",
        used_kleynodu=use_kleynodu
    )
    db.add(attack)
    
    # Update Redis for real-time leaderboards
    redis = get_redis()
    await redis.zincrby(f"boss:{boss_id}:attackers", damage, str(current_user.id))
    await redis.set(f"boss:{boss_id}:health", boss.current_health)
    
    # Check defeat
    if boss.current_health <= 0:
        boss.status = "defeated"
        await _distribute_rewards(boss_id, db)
    
    await db.commit()
    
    # Track
    await analytics.track(TrackedEvent(
        name="boss_attack",
        user_id=current_user.id,
        session_id=None,
        properties={
            "boss_id": boss_id,
            "damage": damage,
            "premium": use_kleynodu > 0
        }
    ))
    
    # Broadcast update
    await publish_event(f"boss:{boss_id}:update", {
        "boss_id": boss_id,
        "health": boss.current_health,
        "last_attacker": current_user.id,
        "damage_dealt": damage
    })
    
    return {
        "damage_dealt": damage,
        "boss_health_remaining": boss.current_health,
        "boss_defeated": boss.status == "defeated"
    }


async def _distribute_rewards(boss_id: int, db: AsyncSession):
    """Distribute rewards when boss is defeated."""
    redis = get_redis()
    
    # Get final standings
    attackers = await redis.zrevrange(
        f"boss:{boss_id}:attackers", 0, -1, withscores=True
    )
    
    total_damage = sum(dmg for _, dmg in attackers)
    
    rewards = []
    for rank, (user_id, damage) in enumerate(attackers[:50], 1):  # Top 50
        damage_share = damage / total_damage if total_damage > 0 else 0
        
        # Calculate rewards
        chervontsi_reward = int(1000000 * damage_share * (1.5 if rank <= 10 else 1.0))
        kleynodu_reward = int(1000 * damage_share * (2.0 if rank <= 3 else 1.0))
        
        # Store for claim
        await redis.hset(f"boss:{boss_id}:rewards", user_id, json.dumps({
            "chervontsi": chervontsi_reward,
            "kleynodu": kleynodu_reward,
            "rank": rank,
            "damage": damage
        }))
        
        # Notify
        await publish_event(f"user:{user_id}:reward", {
            "type": "boss_defeat",
            "boss_id": boss_id,
            "rank": rank
        })


@router.websocket("/live/{boss_id}")
async def boss_live_updates(
    websocket: WebSocket,
    boss_id: int
):
    """WebSocket for live boss updates."""
    await websocket.accept()
    
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"boss:{boss_id}:update")
    
    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message:
                await websocket.send_text(message["data"])
    except Exception:
        await pubsub.unsubscribe(f"boss:{boss_id}:update")
        await websocket.close()