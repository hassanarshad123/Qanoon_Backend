import asyncpg

from app.config import settings

pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    """Create the asyncpg connection pool. Called once at app startup."""
    global pool
    # Convert Neon-style URLs: postgres:// -> postgresql://
    dsn = settings.database_url
    if dsn.startswith("postgres://"):
        dsn = dsn.replace("postgres://", "postgresql://", 1)
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,  # Neon requires this
    )
    return pool


async def close_pool() -> None:
    """Close the pool. Called at app shutdown."""
    global pool
    if pool:
        await pool.close()
        pool = None


def get_pool() -> asyncpg.Pool:
    """Get the active pool. Raises if not initialized."""
    if pool is None:
        raise RuntimeError("Database pool not initialized — call init_pool() first")
    return pool
