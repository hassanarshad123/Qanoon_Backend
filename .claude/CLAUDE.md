# QanoonAI Backend — Python/FastAPI

This file provides context for Claude Code sessions working on the backend in isolation.

## Tech Stack
- **Framework:** FastAPI 0.115+ with async/await throughout
- **Database:** Neon PostgreSQL via `asyncpg` (pool in `app/core/database.py`)
- **Cache:** Upstash Redis via `redis.asyncio` (TLS connection in `app/core/redis.py`)
- **AI:** Anthropic Claude (`app/services/anthropic_client.py`), Voyage AI for embeddings (`app/services/voyage_client.py`)
- **Auth:** JWT tokens validated in `app/core/auth.py` (shared `AUTH_SECRET` with Next.js frontend)
- **Storage:** AWS S3 via boto3 (`app/services/storage_service.py`)
- **Config:** `pydantic-settings` with `.env` file (`app/config.py`)

## Directory Structure
```
backend/app/
├── main.py              # FastAPI app, lifespan, middleware, router registration
├── config.py            # Settings (pydantic-settings, env vars)
├── core/
│   ├── auth.py          # JWT validation, get_current_user dependency
│   ├── database.py      # asyncpg pool (init_pool, close_pool, get_pool)
│   ├── redis.py         # Redis client (init_redis, close_redis, get_redis)
│   ├── exceptions.py    # AppError hierarchy + exception handlers
│   ├── middleware.py     # TimingMiddleware (request duration logging)
│   └── streaming.py     # SSE streaming helpers for AI responses
├── models/              # Pydantic request/response models
├── routers/             # FastAPI APIRouters (one per domain)
├── repositories/        # Database queries (SQL via asyncpg)
├── services/            # Business logic + external API clients
├── rag/                 # RAG search pipeline
└── prompts/             # AI prompt templates
```

## Key Patterns

### Repository Pattern
All database access goes through `repositories/`. Routers never execute SQL directly.
```python
# routers/briefs.py
result = await briefs_repo.get_by_id(pool, brief_id, user_id)

# repositories/briefs.py
async def get_by_id(pool, brief_id: str, user_id: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT ... WHERE id = $1 AND user_id = $2", brief_id, user_id)
```

### Dependency Injection
```python
from app.core.auth import get_current_user, SessionUser
from app.core.database import get_pool

@router.get("/items")
async def list_items(user: SessionUser = Depends(get_current_user), pool=Depends(get_pool)):
    ...
```

### Error Handling
Raise `AppError` subclasses — they're automatically converted to JSON responses:
```python
from app.core.exceptions import NotFoundError, ForbiddenError
raise NotFoundError("Brief not found")  # → 404
raise ForbiddenError("Not your brief")  # → 403
```

### Streaming AI Responses
Use `stream_anthropic()` from `app/core/streaming.py` for SSE endpoints.

## Commands
```bash
# Development
cd backend && uvicorn app.main:app --reload --port 8000

# Linting
cd backend && ruff check app/

# Production (EC2)
cd backend && gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 3 -b 0.0.0.0:8000
```

## Rules
1. **Always use parameterized queries** (`$1`, `$2`) — never f-strings for SQL
2. **All endpoints require auth** except `/api/v1/health` and `/api/v1/auth/*`
3. **Use `Depends(get_pool)`** to get the database pool — never import the global directly
4. **Neon requires `statement_cache_size=0`** in the pool config
5. **Redis URL conversion:** Upstash gives HTTPS URLs, `redis.py` converts to `rediss://` for TLS
6. **Type hints everywhere** — Pydantic models for request/response, type annotations on functions
7. **Routers are prefixed** with `/api/v1` in `main.py` — router files use relative paths

## Environment Variables (required)
- `DATABASE_URL` — Neon PostgreSQL connection string
- `AUTH_SECRET` — JWT secret (must match Next.js `AUTH_SECRET`)
- `ANTHROPIC_API_KEY` — Claude API key
- `VOYAGE_API_KEY` — Voyage AI embeddings key (optional)
- `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` — Redis (optional)
- `CORS_ORIGINS` — Comma-separated allowed origins

## Relation to Frontend
- Frontend `lib/api/*.ts` modules call these endpoints
- Types should stay in sync: `backend/app/models/` ↔ `lib/types/`
- Auth tokens are JWT issued by NextAuth, validated here with the same secret
