"""
Redis client for caching, sessions, pub/sub, and real-time features.
"""
import json
from typing import Optional, Any, List

import redis.asyncio as redis

from config import settings

# Global redis client
redis_client: Optional[redis.Redis] = None


def _create_redis_client() -> redis.Redis:
    """
    Create redis client from URL.
    NOTE: redis-py creates the client object without doing network I/O immediately.
    Actual connection happens on first command.
    """
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


async def init_redis():
    """Initialize Redis connection (idempotent)."""
    global redis_client
    if redis_client is None:
        redis_client = _create_redis_client()


async def close_redis():
    """Close Redis connection."""
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None


def get_redis() -> redis.Redis:
    """
    Get Redis client instance.
    Lazy-init to avoid startup/import errors (e.g., when modules are imported before lifespan runs).
    """
    global redis_client
    if redis_client is None:
        redis_client = _create_redis_client()
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


async def leaderboard_get_range(
    key: str = "global:glory",
    start: int = 0,
    stop: int = 99
) -> List[tuple]:
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
    r = get_redis()
    pipe = r.pipeline()
    now = await r.time()
    current = now[0]  # seconds
    window_key = f"{key}:{current // window}"

    pipe.incr(window_key)
    pipe.expire(window_key, window + 1)
    results = await pipe.execute()

    count = results[0]
    return count <= max_requests
