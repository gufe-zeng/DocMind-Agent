import asyncio
from time import perf_counter
from typing import Awaitable, Callable

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.storage.postgres import check_postgres
from app.storage.qdrant import check_qdrant
from app.storage.redis import check_redis

router = APIRouter(tags=["health"])


async def _run_check(
    name: str,
    check: Callable[[], Awaitable[None]],
) -> tuple[str, dict[str, object]]:
    started = perf_counter()
    try:
        await check()
        return name, {
            "status": "up",
            "latency_ms": round((perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        return name, {
            "status": "down",
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "error": f"{type(exc).__name__}: {exc}",
        }


@router.get("/health")
async def health() -> JSONResponse:
    settings = get_settings()

    checks = await asyncio.gather(
        _run_check(
            "postgres",
            lambda: check_postgres(settings.postgres_dsn),
        ),
        _run_check(
            "redis",
            lambda: check_redis(settings.redis_url),
        ),
        _run_check(
            "qdrant",
            lambda: check_qdrant(settings.qdrant_url, settings.qdrant_api_key),
        ),
    )

    dependencies = dict(checks)
    healthy = all(item["status"] == "up" for item in dependencies.values())

    payload = {
        "status": "ok" if healthy else "degraded",
        "stage": "M0",
        "dependencies": dependencies,
    }

    return JSONResponse(
        status_code=200 if healthy else 503,
        content=payload,
    )
