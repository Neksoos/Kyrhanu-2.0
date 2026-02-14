"""
Guild system router.
Clans, wars, chat (WebSocket upgrade).
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.sql import func

from database import get_db
from models import User, Guild, GuildMember, GuildWar
from services.analytics import analytics, TrackedEvent
from routers.auth import get_current_user
from redis_client import get_redis, publish_event

router = APIRouter()


@router.post("/create")
async def create_guild(
    name: str,
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Create new guild (costs kleynodu)."""
    COST = 1000
    
    if current_user.kleynodu < COST:
        raise HTTPException(status_code=402, detail=f"Need {COST} kleynodu")
    
    # Check not in guild
    if current_user.guild_membership:
        raise HTTPException(status_code=400, detail="Already in guild")
    
    # Validate
    if len(name) < 3 or len(name) > 50:
        raise HTTPException(status_code=400, detail="Name 3-50 chars")
    
    current_user.kleynodu -= COST
    
    guild = Guild(
        name=name,
        tag=tag[:10] if tag else None,
        created_by=current_user.id,
        member_count=1
    )
    db.add(guild)
    await db.flush()
    
    member = GuildMember(
        guild_id=guild.id,
        user_id=current_user.id,
        role="leader"
    )
    db.add(member)
    await db.commit()
    
    await analytics.track(TrackedEvent(
        name="guild_join",
        user_id=current_user.id,
        session_id=None,
        properties={"guild_id": guild.id, "created": True}
    ))
    
    return {
        "guild_id": guild.id,
        "name": guild.name,
        "tag": guild.tag,
        "role": "leader"
    }


@router.post("/join")
async def join_guild(
    guild_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Join existing guild."""
    if current_user.guild_membership:
        raise HTTPException(status_code=400, detail="Already in guild")
    
    guild = await db.get(Guild, guild_id)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")
    
    if guild.member_count >= guild.max_members:
        raise HTTPException(status_code=400, detail="Guild full")
    
    member = GuildMember(
        guild_id=guild_id,
        user_id=current_user.id,
        role="member"
    )
    guild.member_count += 1
    
    db.add(member)
    await db.commit()
    
    await analytics.track(TrackedEvent(
        name="guild_join",
        user_id=current_user.id,
        session_id=None,
        properties={"guild_id": guild_id, "created": False}
    ))
    
    # Notify guild
    await publish_event(f"guild:{guild_id}:join", {
        "user_id": current_user.id,
        "username": current_user.username
    })
    
    return {"success": True, "guild_name": guild.name}


@router.get("/my")
async def get_my_guild(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get user's guild info."""
    if not current_user.guild_membership:
        return {"in_guild": False}
    
    guild = current_user.guild_membership.guild
    
    # Get members
    result = await db.execute(
        select(GuildMember, User).join(User).where(GuildMember.guild_id == guild.id)
    )
    members = []
    for member, user in result.all():
        members.append({
            "user_id": user.id,
            "username": user.username,
            "role": member.role,
            "contribution": member.contribution_points
        })
    
    return {
        "in_guild": True,
        "guild": {
            "id": guild.id,
            "name": guild.name,
            "tag": guild.tag,
            "members": members,
            "total_glory": guild.total_glory,
            "war_wins": guild.war_wins,
            "war_losses": guild.war_losses,
            "current_war": guild.current_war_id
        },
        "my_role": current_user.guild_membership.role
    }


@router.websocket("/chat/{guild_id}")
async def guild_chat(
    websocket: WebSocket,
    guild_id: int,
    token: str
):
    """
    WebSocket endpoint for guild chat.
    Requires valid JWT token.
    """
    await websocket.accept()
    
    # Validate token
    try:
        from jose import jwt
        from config import settings
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    # Verify membership
    from database import async_session_maker
    async with async_session_maker() as db:
        result = await db.execute(
            select(GuildMember).where(
                and_(GuildMember.guild_id == guild_id, GuildMember.user_id == user_id)
            )
        )
        if not result.scalar_one_or_none():
            await websocket.close(code=4002, reason="Not in guild")
            return
    
    # Subscribe to Redis pub/sub for this guild
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"guild:{guild_id}:chat")
    
    # Send recent history
    history = await redis.lrange(f"guild:{guild_id}:history", -50, -1)
    for msg in history:
        await websocket.send_text(msg)
    
    try:
        while True:
            # Receive from client
            data = await websocket.receive_text()
            
            # Validate and broadcast
            message = {
                "user_id": user_id,
                "text": data[:500],  # Limit length
                "timestamp": datetime.utcnow().isoformat()
            }
            msg_json = json.dumps(message)
            
            # Store history
            await redis.lpush(f"guild:{guild_id}:history", msg_json)
            await redis.ltrim(f"guild:{guild_id}:history", 0, 99)
            
            # Publish
            await redis.publish(f"guild:{guild_id}:chat", msg_json)
            
    except WebSocketDisconnect:
        await pubsub.unsubscribe(f"guild:{guild_id}:chat")