import asyncpg

from app.core.database import get_pool


async def fetch_one(query: str, *args) -> asyncpg.Record | None:
    pool = get_pool()
    return await pool.fetchrow(query, *args)


async def fetch_all(query: str, *args) -> list[asyncpg.Record]:
    pool = get_pool()
    return await pool.fetch(query, *args)


async def execute(query: str, *args) -> str:
    pool = get_pool()
    return await pool.execute(query, *args)
