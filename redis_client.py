"""
Redis client for caching, sessions, pub/sub, and real-time features.
"""
import json
import redis.asyncio as redis
from typing import Optional, Any, List
from config import settings

# Global redis client
redis_client: Optional[redis.Redis] = None


async def init_redis():
    """Initialize Redis connection."""
    global redis_client
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


async def close_redis():
    """Close Redis connection."""
    global redis_client
    if redis_client:
        await redis_client.close()


def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    if redis_client is None:
        raise RuntimeError("Redis not initialized")
    return redis_client


# Cache helpers
async def cache_get(key: str) -> Optional[Any]:
    """Get value from cache."""
    data = await get_redis().get(key)
    if data:
        return json.loads(data)
    return None


async def cache_set(key: str, value: Any, expire: int = 300):
    """Set value in cache with expiration (seconds)."""
    await get_redis().setex(key, expire, json.dumps(value))


async def cache_delete(key: str):
    """Delete key from cache."""
    await get_redis().delete(key)


# Leaderboard helpers
async def leaderboard_add(score: float, member: str, key: str = "global:glory"):
    """Add score to sorted set leaderboard."""
    await get_redis().zadd(key, {member: score})


async def leaderboard_get_range(key: str = "global:glory", start: int = 0, stop: int = 99) -> List[tuple]:
    """Get leaderboard range with scores."""
    results = await get_redis().zrevrange(key, start, stop, withscores=True)
    return [(member, int(score)) for member, score in results]


async def leaderboard_get_rank(member: str, key: str = "global:glory") -> Optional[int]:
    """Get rank of member (0-indexed)."""
    rank = await get_redis().zrevrank(key, member)
    return rank


# Pub/Sub for live events
async def publish_event(channel: str, data: dict):
    """Publish event to channel."""
    await get_redis().publish(channel, json.dumps(data))


# Session/Rate limiting
async def rate_limit_check(key: str, max_requests: int, window: int) -> bool:
    """Check if request is within rate limit."""
    pipe = get_redis().pipeline()
    now = await get_redis().time()
    current = now[0]  # seconds
    window_key = f"{key}:{current // window}"
    
    pipe.incr(window_key)
    pipe.expire(window_key, window + 1)
    results = await pipe.execute()
    
    count = results[0]
    return count <= max_requests