import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.database import init_pool, close_pool
from app.core.redis import init_redis, close_redis
from app.core.exceptions import register_exception_handlers
from app.core.middleware import TimingMiddleware
from app.routers import (
    health, auth, profiles, onboarding, activity, notes, documents,
    briefs, judgments, research, dashboard, case_law, admin,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("qanoonai")

# Initialize Sentry (must be before FastAPI app creation)
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        enable_tracing=True,
    )
    logger.info("Sentry initialized (env=%s)", settings.sentry_environment)
else:
    logger.info("Sentry not configured — error tracking disabled.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    # --- Startup ---
    logger.info("Initializing database pool...")
    await init_pool()
    logger.info("Database pool ready.")

    redis = await init_redis()
    if redis:
        logger.info("Redis connected.")
    else:
        logger.warning("Redis not configured — caching disabled.")

    yield

    # --- Shutdown ---
    logger.info("Shutting down...")
    await close_redis()
    await close_pool()
    logger.info("Shutdown complete.")


app = FastAPI(
    title="QanoonAI API",
    version="0.1.0",
    docs_url="/api/v1/docs",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request timing
app.add_middleware(TimingMiddleware)

# Exception handlers
register_exception_handlers(app)

# --- Routers ---
app.include_router(health.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(profiles.router, prefix="/api/v1")
app.include_router(onboarding.router, prefix="/api/v1")
app.include_router(activity.router, prefix="/api/v1")
app.include_router(notes.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(briefs.router, prefix="/api/v1")
app.include_router(judgments.router, prefix="/api/v1")
app.include_router(research.router, prefix="/api/v1")
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(case_law.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
