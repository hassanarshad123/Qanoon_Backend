from fastapi import APIRouter

from app.core.database import get_pool
from app.core.redis import get_redis

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """Check database and Redis connectivity."""
    checks: dict = {"status": "ok"}

    # Database
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            checks["database"] = "connected" if result == 1 else "error"
    except Exception as e:
        checks["database"] = f"error: {e}"
        checks["status"] = "degraded"

    # Redis
    redis = get_redis()
    if redis:
        try:
            pong = await redis.ping()
            checks["redis"] = "connected" if pong else "error"
        except Exception as e:
            checks["redis"] = f"error: {e}"
            checks["status"] = "degraded"
    else:
        checks["redis"] = "not configured"

    return checks
