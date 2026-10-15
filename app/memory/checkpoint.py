"""M4a: LangGraph's official async PostgreSQL checkpointer.

State snapshots after LangGraph nodes are persisted by AsyncPostgresSaver.
This is not a home-grown checkpoint table. It is initialized once in the
FastAPI lifespan and reused for multiple requests.
"""

from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


@asynccontextmanager
async def open_checkpointer(postgres_dsn: str):
    async with AsyncPostgresSaver.from_conn_string(postgres_dsn) as saver:
        await saver.setup()
        yield saver


def thread_config(session_id: str) -> dict:
    return {
        "configurable": {"thread_id": session_id},
        "recursion_limit": 30,
    }
