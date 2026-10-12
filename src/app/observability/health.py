from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.settings import Settings, get_settings
from src.app.database.session import get_db_session

health_router = APIRouter(prefix="/health", tags=["Health & Observability"])


@health_router.get("", status_code=status.HTTP_200_OK)
@health_router.get("/", status_code=status.HTTP_200_OK)
@health_router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> dict[str, str]:
    """Basic liveness probe checking if HTTP server process is running."""
    return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}


@health_router.get("/ready")
async def readiness_check(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    """Readiness probe checking database and redis connectivity."""
    checks: dict[str, Any] = {
        "database": "unknown",
        "redis": "unknown",
    }
    is_ready = True

    # 1. Database connection check
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"
        is_ready = False

    # 2. Redis connection check
    try:
        redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        ping_result = await redis_client.ping()
        await redis_client.aclose()
        if ping_result:
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "unhealthy: ping returned false"
            is_ready = False
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"
        is_ready = False

    response_payload = {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": datetime.now(UTC).isoformat(),
        "environment": settings.ENVIRONMENT,
        "components": checks,
    }

    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=response_payload)
