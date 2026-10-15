"""M8 observability unit contracts, without PostgreSQL, Qwen or Docker."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from prometheus_client import generate_latest

from app.observability.metrics import safe_tool_name, observe_request
from app.observability.tracing import (
    RequestTrace, current_trace, node_span, observed_endpoint,
    record_llm_attempt, record_llm_completion,
    timed_rag, timed_retrieval, timed_rerank,
)
from app.observability.storage import _migration_sql


class FakePool:
    def __init__(self):
        self.calls = []

    async def execute(self, sql, *params):
        self.calls.append((sql, params))
        return "INSERT 0 1"


class FakeResponse:
    def __init__(self, *, status="answered"):
        self.status = status
        self.session_id = uuid4()
        self.request_id = uuid4()
        self.trace_id = None
        self.intent = "mcp_find_clause"
        self.steps = 1
        self.tools_called = ["mcp_find_clause"]
        self.tool_events = [{
            "tool": "mcp_find_clause", "status": "ok",
            "attempts": 1, "retries": 0,
            "timeout_seconds": 60, "duration_ms": 3.2,
            "unsafe_content": "should-never-save",
        }]


def fake_http(pool):
    return SimpleNamespace(app=SimpleNamespace(
        state=SimpleNamespace(trace_pool=pool)
    ))


@pytest.mark.asyncio
async def test_decorated_endpoint_preserves_identity_nodes_and_redacts():
    pool = FakePool()

    @observed_endpoint("chat")
    async def handler(*, request, http_request):
        with node_span("route"):
            pass
        with node_span("call_tool", tool="mcp_find_clause"):
            record_llm_attempt()
            record_llm_completion(5, 7)
        return FakeResponse()

    response = await handler(request=SimpleNamespace(session_id=None),
                             http_request=fake_http(pool))
    assert isinstance(response.trace_id, UUID)
    assert len(pool.calls) == 1
    sql, params = pool.calls[0]
    assert "INSERT INTO agent_traces" in sql
    assert params[0] == response.trace_id
    assert params[1] == response.request_id
    assert params[3] == "chat"
    assert params[4] == "answered"
    assert params[14] == 1
    assert params[15] == 5 and params[16] == 7
    nodes = json.loads(params[12])
    events = json.loads(params[13])
    assert [n["node"] for n in nodes] == ["route", "call_tool"]
    assert nodes[1]["llm_calls"] == 1
    assert nodes[1]["prompt_tokens"] == 5
    assert nodes[1]["completion_tokens"] == 7
    assert events[0]["tool"] == "mcp_find_clause"
    assert "unsafe_content" not in json.dumps(events)
    assert current_trace() is None


@pytest.mark.asyncio
async def test_http_errors_are_recorded_with_only_exception_type():
    pool = FakePool()

    @observed_endpoint("approval")
    async def handler(*, body, http_request):
        with node_span("route"):
            pass
        raise HTTPException(status_code=403, detail="private-user-data")

    with pytest.raises(HTTPException):
        await handler(body=SimpleNamespace(session_id=uuid4()),
                      http_request=fake_http(pool))
    assert len(pool.calls) == 1
    sql, params = pool.calls[0]
    assert params[3] == "approval"
    assert params[4] == "http_error"
    assert params[5] == 403
    assert params[-1] == "HTTPException"
    assert "private-user-data" not in repr(params)


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_node_or_token_state():
    pool = FakePool()

    @observed_endpoint("chat")
    async def handler(*, request, http_request):
        with node_span("route"):
            await asyncio.sleep(0)
            record_llm_attempt()
            record_llm_completion(2, 3)
        return FakeResponse()

    responses = await asyncio.gather(*[
        handler(request=SimpleNamespace(session_id=None),
                http_request=fake_http(pool))
        for _ in range(4)
    ])
    assert len(pool.calls) == 4
    assert len({r.trace_id for r in responses}) == 4
    assert all(p[15] == 2 and p[16] == 3 for _, p in pool.calls)
    assert all(len(json.loads(p[12])) == 1 for _, p in pool.calls)
    assert current_trace() is None


@pytest.mark.asyncio
async def test_unreported_llm_tokens_are_null_not_zero():
    pool = FakePool()

    @observed_endpoint("chat")
    async def handler(*, request, http_request):
        with node_span("route"):
            record_llm_attempt()
            record_llm_completion(None, None)
        return FakeResponse()

    await handler(request=SimpleNamespace(session_id=None), http_request=fake_http(pool))
    assert pool.calls[0][1][14] == 1
    assert pool.calls[0][1][15] is None
    assert pool.calls[0][1][16] is None
    node = json.loads(pool.calls[0][1][12])[0]
    assert node["prompt_tokens"] is None


def test_prometheus_metrics_use_fixed_labels_and_export_frozen_names():
    assert safe_tool_name("mcp_find_clause") == "mcp_find_clause"
    assert safe_tool_name("user-input") == "other"
    observe_request("chat", status="answered", http_status=200,
                    seconds=0.01, steps=2,
                    tools_called=["mcp_find_clause"],
                    tool_events=[{
                        "tool": "mcp_find_clause", "status": "fallback",
                        "attempts": 3, "duration_ms": 10,
                    }])
    scrape = generate_latest().decode()
    for name in (
        "agent_requests_total", "agent_success_total", "agent_failures_total",
        "agent_steps_count", "agent_e2e_latency_seconds_count",
        "tool_calls_total", "tool_failures_total", "tool_latency_seconds_count",
        "rag_latency_seconds_count", "retrieval_latency_seconds_count",
        "rerank_latency_seconds_count",
    ):
        assert name in scrape


@pytest.mark.asyncio
async def test_rag_retrieval_and_rerank_stage_timers_are_callable():
    @timed_rag
    async def rag():
        await asyncio.sleep(0)

    @timed_retrieval
    async def retrieval():
        await asyncio.sleep(0)

    @timed_rerank
    def rerank():
        return 7

    await rag()
    await retrieval()
    assert rerank() == 7


def test_migration_and_docker_cache_contracts():
    sql = _migration_sql()
    assert "CREATE TABLE IF NOT EXISTS agent_traces" in sql
    assert "node_events JSONB" in sql
    assert "prompt_tokens INTEGER" in sql
    assert "query_text" not in sql and "answer_text" not in sql
    project_root = Path(__file__).resolve().parents[2]
    docker = (project_root / "Dockerfile").read_text(encoding="utf-8")
    assert docker.index("COPY pyproject.toml /tmp/") < docker.index(
        "pip install --no-cache-dir -r /tmp/docmind-deps.txt"
    ) < docker.index("COPY app ./app")
    assert "pip install --no-deps --no-build-isolation ." in docker
    assert "COPY scripts/check_m8.py" in docker
