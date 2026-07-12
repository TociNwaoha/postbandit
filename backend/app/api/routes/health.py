import logging

import redis as redis_lib
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import engine

logger = logging.getLogger(__name__)
router = APIRouter()


def _redis_client() -> redis_lib.Redis:
    return redis_lib.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)


@router.get("/health")
@router.get("/api/health")
async def health_check():
    checks: dict[str, bool] = {}

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as exc:
        checks["database"] = False
        logger.warning("[health] DB check failed: %s", exc)

    try:
        _redis_client().ping()
        checks["redis"] = True
    except Exception as exc:
        checks["redis"] = False
        logger.warning("[health] Redis check failed: %s", exc)

    all_healthy = all(checks.values())
    return JSONResponse(
        status_code=200 if all_healthy else 503,
        content={
            "status": "ok" if all_healthy else "degraded",
            "version": "1.0.0",
            "checks": checks,
            # Backward-compatible fields used by existing scripts and dashboards.
            "database": "connected" if checks.get("database") else "disconnected",
            "redis": "connected" if checks.get("redis") else "disconnected",
        },
    )
