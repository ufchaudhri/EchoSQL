"""
EchoSQL — FastAPI backend entry point.
"""

# Observability must be initialised before any other module creates a logger
# or tracer, so that all log records and spans use the configured provider.
from observability import configure_observability
configure_observability()

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import API_HOST, API_PORT
from services.redis_cache import get_redis_cache
from routes.query import router as query_router
from routes.schema import router as schema_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cache = get_redis_cache()
    if cache.connect():
        logger.info("Redis connected",
                    extra={"event": "startup.redis", "status": "ok"})
    else:
        logger.warning("Redis unavailable — running without cache",
                       extra={"event": "startup.redis", "status": "unavailable"})
    yield
    cache.close()
    logger.info("Redis connection closed", extra={"event": "shutdown.redis"})


app = FastAPI(
    title="EchoSQL API",
    description="Natural-language → SQL query converter with Redis caching",
    version="1.0.0",
    lifespan=lifespan,
)

# FastAPI auto-instrumentation: creates an HTTP span for every incoming request
# (acts as the parent span for all echosql.* child spans)
try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI OTel instrumentation active",
                extra={"event": "startup.otel"})
except ImportError:
    logger.warning("opentelemetry-instrumentation-fastapi not installed — "
                   "HTTP root spans will be missing",
                   extra={"event": "startup.otel", "status": "missing"})

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://localhost:3004",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query_router)
app.include_router(schema_router)


@app.get("/health")
async def health_check():
    """Return status of all dependent services."""
    from services.db_service import check_db_health
    from services.llm_service import check_ollama_health

    cache = get_redis_cache()
    db_ok = await check_db_health()
    ollama_ok = await check_ollama_health()

    logger.info("Health check",
                extra={"event": "health.check",
                       "db": db_ok, "ollama": ollama_ok,
                       "redis": cache.get_stats().get("connected", False)})

    return {
        "status": "healthy",
        "services": {
            "redis":    cache.get_stats(),
            "database": {"connected": db_ok},
            "ollama":   {"connected": ollama_ok},
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=API_HOST, port=API_PORT, reload=True, log_level="info")
