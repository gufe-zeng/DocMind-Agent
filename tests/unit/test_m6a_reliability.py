"""M6a tool reliability: retry ceiling, errors, fail-closed and state traces."""

import asyncio
from uuid import uuid4

import httpx
import pytest

from app.agent.graph import build_agent_graph
from app.agent.reliability import (
    ToolPolicy,
    execute_read_only_tool,
    retryable_error,
)


@pytest.mark.asyncio
async def test_two_transient_retries_then_success():
    calls = []

    async def flaky(name, *, arguments):
        calls.append(name)
        if len(calls) < 3:
            raise httpx.ConnectError("synthetic connection failure")
        return {"tool": name, "status": "answered", "documents": []}

    out = await execute_read_only_tool(
        "query_document_metadata",
        arguments={"document_id": None},
        executor=flaky,
        policy=ToolPolicy(timeout_seconds=0.2, backoff_seconds=0),
    )
    assert len(calls) == 3
    assert out.result["tool"] == "query_document_metadata"
    assert out.result["status"] == "answered"
    assert out.event["attempts"] == 3
    assert out.event["retries"] == 2
    assert out.event["status"] == "ok"


@pytest.mark.asyncio
async def test_exhausted_retry_returns_nonfactual_fallback():
    calls = 0

    async def unavailable(name, *, arguments):
        nonlocal calls
        calls += 1
        raise ConnectionError("temporary database connection failure")

    out = await execute_read_only_tool(
        "query_document_metadata",
        arguments={},
        executor=unavailable,
        policy=ToolPolicy(timeout_seconds=0.2, backoff_seconds=0),
    )
    assert calls == 3
    assert out.result["status"] == "tool_unavailable"
    assert out.result["sources"] == []
    assert out.result["answer"].find("无法确认") >= 0
    assert out.event["error_type"] == "ConnectionError"
    assert out.event["retries"] == 2


@pytest.mark.asyncio
async def test_slow_coroutine_times_out_without_retrying_forever():
    calls = 0

    async def slow(name, *, arguments):
        nonlocal calls
        calls += 1
        await asyncio.sleep(1)
        return {"tool": name, "status": "answered"}

    out = await execute_read_only_tool(
        "query_document_metadata", arguments={}, executor=slow,
        policy=ToolPolicy(timeout_seconds=0.01, backoff_seconds=0),
    )
    assert calls == 3
    assert out.result["status"] == "tool_unavailable"
    assert out.event["error_type"] == "TimeoutError"
    assert out.event["attempts"] == 3


@pytest.mark.asyncio
async def test_invalid_inputs_and_software_defects_not_retried():
    calls = 0

    async def invalid(name, *, arguments):
        nonlocal calls
        calls += 1
        raise ValueError("invalid document ID")

    with pytest.raises(ValueError):
        await execute_read_only_tool(
            "mcp_get_document", arguments={}, executor=invalid,
        )
    assert calls == 1

    async def bug(name, *, arguments):
        raise RuntimeError("source provenance mismatch")

    with pytest.raises(RuntimeError, match="provenance"):
        await execute_read_only_tool(
            "mcp_find_clause", arguments={}, executor=bug,
        )
    assert not retryable_error(RuntimeError("source provenance mismatch"))


@pytest.mark.asyncio
async def test_no_policy_for_approval_protected_writes():
    async def never(name, *, arguments):
        raise AssertionError("A write tool must not be executed here.")

    with pytest.raises(ValueError, match="No read-only reliability policy"):
        await execute_read_only_tool(
            "save_review_note", arguments={}, executor=never
        )


@pytest.mark.asyncio
async def test_graph_exposes_fallback_and_preserves_successful_source(monkeypatch):
    from app.agent.router import PlanDecision
    from app.agent import nodes

    async def plan(query, document_id=None):
        return PlanDecision(
            tools=["query_document_metadata", "mcp_find_clause"],
            source="rules",
        )

    attempts = {}

    async def tool(name, *, arguments):
        attempts[name] = attempts.get(name, 0) + 1
        if name == "query_document_metadata":
            raise httpx.ConnectError("synthetic metadata network failure")
        return {
            "tool": "mcp_find_clause", "mcp_tool": "find_clause",
            "mcp_transport": "stdio", "status": "answered",
            "answer": "违约责任：支付违约金。[S1]",
            "sources": [
                {"id": "S1", "document_id": arguments["document_id"],
                 "chunk_id": "chunk-1", "filename": "contract.txt", "page": None}
            ],
        }

    monkeypatch.setattr(nodes, "plan_tools", plan)
    monkeypatch.setattr(nodes, "invoke_tool", tool)
    result = await build_agent_graph().ainvoke(
        {"query": "通过MCP查找违约责任条款", "document_id": str(uuid4())}
    )
    assert result["status"] == "partial"
    assert result["tools_called"] == [
        "query_document_metadata", "mcp_find_clause",
    ]
    assert result["retry_count"] == 2
    assert result["current_step"] == 2  # retries do not count as graph steps
    assert attempts == {"query_document_metadata": 3, "mcp_find_clause": 1}
    assert result["reliability_events"][0]["status"] == "fallback"
    assert result["reliability_events"][1]["status"] == "ok"
    assert "未找到已上传的文档" not in result["final_answer"]
    assert "工具暂不可用" in result["final_answer"]
    assert "违约责任：支付违约金。[S1]" in result["final_answer"]
    assert result["sources"][0]["chunk_id"] == "chunk-1"


@pytest.mark.asyncio
async def test_all_tool_fallback_is_explicitly_unavailable(monkeypatch):
    from app.agent import nodes

    async def unavailable(name, *, arguments):
        raise httpx.ConnectError("injected")

    monkeypatch.setattr(nodes, "invoke_tool", unavailable)
    result = await build_agent_graph().ainvoke(
        {"query": "列出已上传的文档", "document_id": None}
    )
    assert result["status"] == "tool_unavailable"
    assert result["sources"] == []
    assert "工具暂不可用" in result["final_answer"]
    assert "未找到已上传的文档" not in result["final_answer"]
    assert result["retry_count"] == 2
