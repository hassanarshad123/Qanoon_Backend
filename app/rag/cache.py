"""Redis cache for RAG search results."""

import json
import hashlib

from app.core.redis import get_redis

TTL_SECONDS = 15 * 60  # 15 minutes


def build_cache_key(options: dict) -> str:
    key_data = json.dumps({
        "q": options.get("query", ""),
        "f": options.get("filters"),
        "l": options.get("limit", 10),
        "o": options.get("offset", 0),
    }, sort_keys=True)
    return f"rag:{hashlib.md5(key_data.encode()).hexdigest()[:16]}"


async def get_cached(key: str) -> list | None:
    redis = get_redis()
    if not redis:
        return None
    try:
        data = await redis.get(key)
        if data:
            return json.loads(data) if isinstance(data, str) else data
    except Exception:
        pass
    return None


async def set_cache(key: str, results: list) -> None:
    redis = get_redis()
    if not redis:
        return
    try:
        await redis.set(key, json.dumps(results), ex=TTL_SECONDS)
    except Exception:
        pass
