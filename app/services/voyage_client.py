"""Voyage AI embeddings with Redis caching."""

import hashlib
import json

from app.config import settings
from app.core.redis import get_redis

EMB_TTL_SECONDS = 24 * 60 * 60  # 24 hours

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not settings.voyage_api_key:
        return None
    import voyageai
    _client = voyageai.Client(api_key=settings.voyage_api_key)
    return _client


def _hash_text(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()[:16]


async def generate_embedding(text: str) -> list[float] | None:
    client = _get_client()
    if not client:
        return None

    redis = get_redis()
    cache_key = f"emb:{_hash_text(text)}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    try:
        result = client.embed([text], model="voyage-law-2")
        embedding = result.embeddings[0] if result.embeddings else None

        if embedding and redis:
            try:
                await redis.set(cache_key, json.dumps(embedding), ex=EMB_TTL_SECONDS)
            except Exception:
                pass

        return embedding
    except Exception:
        return None


async def generate_embeddings(texts: list[str]) -> list[list[float] | None]:
    client = _get_client()
    if not client:
        return [None] * len(texts)

    redis = get_redis()
    results: list[list[float] | None] = [None] * len(texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    if redis:
        try:
            keys = [f"emb:{_hash_text(t)}" for t in texts]
            cached_values = await redis.mget(keys)
            for i, val in enumerate(cached_values):
                if val:
                    results[i] = json.loads(val) if isinstance(val, str) else val
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(texts[i])
        except Exception:
            uncached_indices = list(range(len(texts)))
            uncached_texts = list(texts)
    else:
        uncached_indices = list(range(len(texts)))
        uncached_texts = list(texts)

    if not uncached_texts:
        return results

    try:
        result = client.embed(uncached_texts, model="voyage-law-2")
        embeddings = result.embeddings if result.embeddings else [None] * len(uncached_texts)

        to_cache = {}
        for i, idx in enumerate(uncached_indices):
            emb = embeddings[i] if i < len(embeddings) else None
            results[idx] = emb
            if emb and redis:
                to_cache[f"emb:{_hash_text(uncached_texts[i])}"] = json.dumps(emb)

        if redis and to_cache:
            try:
                pipe = redis.pipeline()
                for k, v in to_cache.items():
                    pipe.set(k, v, ex=EMB_TTL_SECONDS)
                await pipe.execute()
            except Exception:
                pass

        return results
    except Exception:
        return results
