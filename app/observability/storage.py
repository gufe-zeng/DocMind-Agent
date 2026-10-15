"""PostgreSQL durable Agent trace storage with no prompt, answer or credential data."""
import json
from pathlib import Path
from uuid import UUID

import asyncpg

from app.observability.tracing import RequestTrace


def _migration_sql() -> str:
    return (
        Path(__file__).resolve().parents[2] / "migrations" / "004_agent_traces.sql"
    ).read_text(encoding="utf-8")


async def init_trace_schema(dsn: str) -> None:
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        await conn.execute(_migration_sql())
    finally:
        await conn.close()


async def persist_trace(pool: asyncpg.Pool, trace: RequestTrace) -> None:
    """Insert one immutable record per attempt; request ID stays separate from trace ID."""
    await pool.execute(
        """INSERT INTO agent_traces (
            trace_id, request_id, session_id, operation, status, http_status,
            intent, started_at, ended_at, duration_ms, steps, tool_names,
            node_events, tool_events, llm_calls, prompt_tokens,
            completion_tokens, error_type
        ) VALUES (
            $1, $2, $3, $4, $5, $6,
            $7, $8, $9, $10, $11, $12::jsonb,
            $13::jsonb, $14::jsonb, $15, $16, $17, $18
        )""",
        trace.trace_id, trace.request_id, trace.session_id, trace.operation,
        trace.status, trace.http_status, trace.intent, trace.started_at,
        trace.ended_at, trace.duration_ms, trace.steps,
        json.dumps(trace.tools_called),
        json.dumps(trace.node_events),
        json.dumps(trace.tool_events),
        trace.llm_calls, trace.prompt_tokens, trace.completion_tokens,
        trace.error_type,
    )


async def fetch_trace(pool: asyncpg.Pool, trace_id: UUID) -> dict | None:
    row = await pool.fetchrow(
        """SELECT trace_id, request_id, session_id, operation, status,
                  http_status, intent, node_events, tool_events, tool_names,
                  llm_calls, prompt_tokens, completion_tokens,
                  started_at, ended_at, duration_ms, steps, error_type
             FROM agent_traces WHERE trace_id = $1""",
        trace_id,
    )
    if row is None:
        return None
    result = dict(row)
    for column in ("node_events", "tool_events", "tool_names"):
        if isinstance(result[column], str):
            result[column] = json.loads(result[column])
    return result
