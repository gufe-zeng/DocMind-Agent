"""M8 two-phase Docker acceptance: Agent metrics, durable redacted spans and restart.

The Windows BAT prepares real Agent/MCP and HITL traffic, restarts ONLY API,
then checks PostgreSQL trace persistence across the restart. No Qwen or
additional model download is needed for the BASE acceptance.
"""
import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import httpx

from app.core.config import get_settings


STATE_PATH = Path("/app/data/uploads/.m8_acceptance.json")
CONTRACT = (
    "甲方：示例客户有限公司。\n"
    "乙方：示例服务有限公司。\n"
    "付款条款：服务验收合格后甲方在三十日内付款。\n"
    "违约责任：逾期付款需依合同约定支付违约金。\n"
)


async def wait_ready(http: httpx.AsyncClient) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 90
    while True:
        try:
            response = await http.get("/health", timeout=5)
            response.raise_for_status()
            assert response.json()["status"] == "ok"
            return
        except (httpx.HTTPError, AssertionError, ValueError) as exc:
            if loop.time() >= deadline:
                raise RuntimeError("M8 API readiness timed out") from exc
            await asyncio.sleep(2)


async def fetch_trace(identifier: str) -> dict:
    conn = await asyncpg.connect(dsn=get_settings().postgres_dsn, timeout=10)
    try:
        row = await conn.fetchrow(
            """SELECT trace_id, request_id, session_id, operation, status,
                      http_status, intent, steps, tool_names, tool_events,
                      node_events, llm_calls, prompt_tokens, completion_tokens
                 FROM agent_traces WHERE trace_id=$1""",
            UUID(identifier),
        )
        assert row is not None, f"Missing durable trace: {identifier}"
        result = dict(row)
        for field in ("node_events", "tool_events", "tool_names"):
            if isinstance(result[field], str):
                result[field] = json.loads(result[field])
        return result
    finally:
        await conn.close()


async def post_json(http: httpx.AsyncClient, url: str, data: dict) -> dict:
    response = await http.post(url, json=data)
    if response.status_code != 200:
        print("Unexpected API failure:", url, response.status_code,
              response.text[:500], flush=True)
    response.raise_for_status()
    return response.json()


def check_identity(reply: dict, row: dict, *, operation: str, status: str) -> None:
    assert UUID(reply["trace_id"]) == row["trace_id"]
    assert UUID(reply["request_id"]) == row["request_id"]
    assert UUID(reply["session_id"]) == row["session_id"]
    assert row["operation"] == operation
    assert row["status"] == status
    assert row["http_status"] == 200
    assert row["llm_calls"] == 0
    assert row["prompt_tokens"] == 0 and row["completion_tokens"] == 0
    # Trace schema stores control-plane metadata, not the contract or review note.
    as_string = json.dumps({
        "node_events": row["node_events"],
        "tool_events": row["tool_events"],
        "tools": row["tool_names"],
    }, ensure_ascii=False)
    assert "示例客户" not in as_string
    assert "逾期付款需" not in as_string


async def prepare() -> None:
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False,
    ) as http:
        await wait_ready(http)
        uploaded = await http.post(
            "/v1/documents",
            files={"file": ("m8_trace.txt", CONTRACT.encode("utf-8"), "text/plain")},
        )
        uploaded.raise_for_status()
        doc_id = uploaded.json()["document_id"]
        indexed = await http.post(f"/v1/documents/{doc_id}/index")
        indexed.raise_for_status()
        assert indexed.json()["status"] == "indexed"
        print("PASS M8 API ready and synthetic document indexed", flush=True)

        metadata = await post_json(http, "/v1/chat", {
            "query": "查询文档信息", "document_id": doc_id,
        })
        assert metadata["status"] == "answered"
        assert metadata["tools_called"] == ["query_document_metadata"]
        row = await fetch_trace(metadata["trace_id"])
        check_identity(metadata, row, operation="chat", status="answered")
        names = [event["node"] for event in row["node_events"]]
        assert names[0] == "route" and names[-1] == "synthesize", names
        assert {"route", "decide", "call_tool", "synthesize"}.issubset(names)
        assert all(
            entry["start_time"] and entry["end_time"] and entry["duration_ms"] >= 0
            for entry in row["node_events"]
        )
        assert len(row["tool_events"]) == 1
        print("PASS durable trace for real LangGraph nodes and PostgreSQL tool", flush=True)

        clause = await post_json(http, "/v1/chat", {
            "query": "通过MCP查找违约责任条款", "document_id": doc_id,
        })
        assert clause["status"] == "answered"
        assert clause["mcp_tools_called"] == ["find_clause"]
        assert clause["sources"] and "[S1]" in clause["answer"]
        clause_row = await fetch_trace(clause["trace_id"])
        check_identity(clause, clause_row, operation="chat", status="answered")
        assert clause_row["tool_names"] == ["mcp_find_clause"]
        assert clause_row["tool_events"][0]["status"] == "ok"
        print("PASS real Agent->MCP trace with source-preserving tool event", flush=True)

        user_id = str(uuid4())
        pending = await post_json(http, "/v1/chat", {
            "query": "保存审核备注：请核验付款和违约条款。",
            "document_id": doc_id, "user_id": user_id,
        })
        assert pending["status"] == "approval_required"
        pending_row = await fetch_trace(pending["trace_id"])
        check_identity(pending, pending_row, operation="chat", status="approval_required")
        assert pending_row["node_events"]
        print("PASS pending HITL graph request is traced without pre-approval write",
              flush=True)

        decided = await post_json(
            http, f"/v1/approvals/{pending['approval_id']}", {
                "decision": "approve", "session_id": pending["session_id"],
                "user_id": user_id,
            },
        )
        assert decided["status"] == "approved" and decided["review_note_id"]
        decided_row = await fetch_trace(decided["trace_id"])
        check_identity(decided, decided_row, operation="approval", status="approved")
        assert any(e["node"] == "call_tool" for e in decided_row["node_events"])
        print("PASS HITL approval checkpoint resume and second durable trace", flush=True)

        before = (await http.get("/metrics")).text
        for metric in (
            'agent_requests_total{operation="chat"}',
            'agent_success_total{operation="approval"}',
            'agent_e2e_latency_seconds_count{operation="chat"}',
            "agent_steps_count", 'tool_calls_total{tool="mcp_find_clause"}',
            'tool_latency_seconds_count{tool="query_document_metadata"}',
            "rag_latency_seconds_count", "retrieval_latency_seconds_count",
            "rerank_latency_seconds_count", "llm_calls_total",
        ):
            # Unlabelled LLM counter is lazily exposed only after a call;
            # it is valid for a no-model workload to be absent or zero.
            if metric == "llm_calls_total":
                continue
            assert metric in before, f"Missing exported Prometheus metric: {metric}"
        print("PASS /metrics exposes request, node/tool and RAG stage families",
              flush=True)

    STATE_PATH.write_text(json.dumps({
        "metadata_trace": metadata["trace_id"],
        "clause_trace": clause["trace_id"],
        "pending_trace": pending["trace_id"],
        "approval_trace": decided["trace_id"],
        "doc_id": doc_id,
    }), encoding="utf-8")
    print("M8 PREPARE PASS - restart only API and verify persisted traces", flush=True)


async def finish() -> None:
    assert STATE_PATH.is_file(), "M8 prepare must run before finish"
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    for field in ("metadata_trace", "clause_trace", "pending_trace", "approval_trace"):
        row = await fetch_trace(state[field])
        assert row["trace_id"] == UUID(state[field])
    print("PASS M8 PostgreSQL Agent traces survive real API restart", flush=True)

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False,
    ) as http:
        await wait_ready(http)
        again = await post_json(http, "/v1/chat", {
            "query": "查询文档信息", "document_id": state["doc_id"],
        })
        assert again["status"] == "answered"
        new_row = await fetch_trace(again["trace_id"])
        check_identity(again, new_row, operation="chat", status="answered")
        assert len(new_row["node_events"]) >= 4
        print("PASS new requests produce traces after API restart", flush=True)
        metrics = (await http.get("/metrics")).text
        assert 'agent_requests_total{operation="chat"}' in metrics
        assert 'agent_success_total{operation="chat"}' in metrics
        print("PASS Prometheus instrumentation active after API restart", flush=True)

    print("M8 OBSERVABILITY PASS", flush=True)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "finish"):
        raise SystemExit("Usage: python scripts/check_m8.py prepare|finish")
    asyncio.run(prepare() if sys.argv[1] == "prepare" else finish())
