"""DocMind Agent FastAPI application and service lifecycle."""

from contextlib import asynccontextmanager

import asyncpg

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from app.agent.graph import build_agent_graph
from app.api.chat import router as chat_router
from app.api.approvals import router as approval_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.memory.checkpoint import open_checkpointer
from app.memory.session import SessionStore
from app.observability.storage import init_trace_schema
from app.storage.postgres import init_documents_schema


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_documents_schema(settings.postgres_dsn)
    from app.memory.long_term import init_memory_schema
    await init_memory_schema(settings.postgres_dsn)
    from app.approvals.storage import init_approval_schema
    await init_approval_schema(settings.postgres_dsn)
    await init_trace_schema(settings.postgres_dsn)
    trace_pool = await asyncpg.create_pool(
        dsn=settings.postgres_dsn, min_size=1, max_size=5, timeout=10
    )
    app.state.trace_pool = trace_pool
    redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    try:
        await redis_client.ping()
        async with open_checkpointer(settings.postgres_dsn) as checkpointer:
            # Uses LangGraph's own PostgreSQL checkpoint schema/migrations.
            app.state.agent_graph = build_agent_graph(checkpointer=checkpointer)
            from app.memory.long_term import LongTermMemory
            app.state.long_term_memory = LongTermMemory()
            app.state.session_store = SessionStore(
                redis_client,
                ttl_seconds=settings.session_ttl_seconds,
                max_turns=settings.session_max_turns,
                lock_seconds=settings.session_lock_seconds,
            )
            yield
    finally:
        await redis_client.aclose()
        await trace_pool.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Traceable RAG Agent for complex document intelligence.",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(approval_router)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": "0.1.0",
        "stage": "M8",
        "status": "running",
    }


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
