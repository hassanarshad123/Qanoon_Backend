"""Gunicorn production config for QanoonAI FastAPI backend.

Tuned for AWS EC2 t3.small (2 vCPU, 2 GB RAM) with SSE streaming endpoints.
"""

# Bind to localhost only — nginx reverse-proxies from :443
bind = "127.0.0.1:8000"

# Workers: 2 * CPU_cores + 1.  t3.small has 2 vCPUs → 3 workers.
# Override via GUNICORN_WORKERS env or --workers flag.
workers = 3

# Uvicorn's async worker — required for FastAPI's async endpoints & SSE
worker_class = "uvicorn.workers.UvicornWorker"

# CRITICAL: asyncpg connection pool is NOT fork-safe.
# Each worker must create its own pool via the FastAPI lifespan handler.
preload_app = False

# SSE streaming endpoints (briefs, judgments, research) hold connections
# open for 30-120+ seconds. Set timeout high enough to avoid killing
# in-progress AI generation streams.
timeout = 300

# On graceful restart (SIGHUP), give workers time to finish active streams
# before forcefully killing them.
graceful_timeout = 180

# Keep-alive for nginx ↔ gunicorn connection reuse
keepalive = 5

# Logging — stdout/stderr so journalctl and docker logs capture everything
accesslog = "-"
errorlog = "-"
loglevel = "info"
