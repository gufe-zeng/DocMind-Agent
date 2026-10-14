from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.storage.postgres import init_documents_schema

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_documents_schema(settings.postgres_dsn)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Traceable RAG Agent for complex document intelligence.",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(documents_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "stage": "M1",
        "status": "running",
    }


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
