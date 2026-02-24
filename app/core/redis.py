import redis.asyncio as aioredis

from app.config import settings

_redis: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis | None:
    """Initialize the async Redis client. Returns None if not configured."""
    global _redis
    url = settings.upstash_redis_rest_url
    token = settings.upstash_redis_rest_token
    if not url or not token:
        return None
    # Upstash provides HTTPS REST URLs, but the redis-py library needs
    # rediss:// (TLS) scheme for direct socket connections.
    redis_url = url.replace("https://", "rediss://").replace("http://", "redis://")
    _redis = aioredis.from_url(
        redis_url,
        password=token,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    # Test connectivity
    try:
        await _redis.ping()
    except Exception:
        _redis = None
        return None
    return _redis


async def close_redis() -> None:
    """Close the Redis connection."""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None


def get_redis() -> aioredis.Redis | None:
    """Get the active Redis client, or None if not configured/connected."""
    return _redis
