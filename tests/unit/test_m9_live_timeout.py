"""M9 LIVE regression: slow BGE CPU inference is bounded and never retried.

The observed failure was three 90-second RAG timeouts (270.3 seconds total)
and zero LLM calls. These tests require no real model, Docker or network.
"""
import asyncio
from types import SimpleNamespace
from time import sleep

import httpx
import pytest
from pydantic import ValidationError

from app.agent.reliability import (
    CPU_RAG_TOOLS, READ_ONLY_POLICIES, ToolPolicy, execute_read_only_tool,
)
from app.core import config
from scripts.check_m9 import live_failure_diagnostic


def test_cpu_rag_has_long_single_attempt_budget_without_changing_other_tools():
    assert CPU_RAG_TOOLS == {"search_documents", "summarize_document"}
    for name in CPU_RAG_TOOLS:
        policy = READ_ONLY_POLICIES[name]
        assert policy.timeout_seconds == 420
        assert policy.max_retries == 0
        assert policy.cpu_inference is True

    metadata = READ_ONLY_POLICIES["query_document_metadata"]
    assert (metadata.timeout_seconds, metadata.max_retries) == (15, 2)
    assert READ_ONLY_POLICIES["mcp_find_clause"].max_retries == 2
    assert READ_ONLY_POLICIES["mcp_search_documents"].max_retries == 2
    assert max(p.max_retries for p in READ_ONLY_POLICIES.values()) <= 2
    with pytest.raises(ValueError):
        ToolPolicy(timeout_seconds=420)
    with pytest.raises(ValueError):
        ToolPolicy(timeout_seconds=421, max_retries=2, cpu_inference=True)
    with pytest.raises(ValueError):
        ToolPolicy(timeout_seconds=601, max_retries=0, cpu_inference=True)


@pytest.mark.asyncio
async def test_cpu_thread_timeout_is_not_launched_three_times():
    starts = 0

    async def unkillable_thread(name, *, arguments):
        nonlocal starts
        starts += 1
        await asyncio.to_thread(sleep, 0.08)
        return {"tool": name, "status": "answered"}

    result = await execute_read_only_tool(
        "search_documents",
        arguments={"query": "synthetic"},
        executor=unkillable_thread,
        policy=ToolPolicy(timeout_seconds=0.005, max_retries=0, cpu_inference=True),
    )
    assert starts == 1
    assert result.event["status"] == "fallback"
    assert result.event["error_type"] == "TimeoutError"
    assert result.event["attempts"] == 1
    assert result.event["retries"] == 0
    assert result.result["status"] == "tool_unavailable"
    assert result.result["sources"] == []
    # The blocked worker is allowed to finish; it is never launched again.
    await asyncio.sleep(0.09)
    assert starts == 1


@pytest.mark.asyncio
async def test_rag_transient_http_failure_is_not_retried_after_cpu_may_have_started():
    starts = 0

    async def intermittent(name, *, arguments):
        nonlocal starts
        starts += 1
        raise httpx.ConnectError("synthetic: model service unavailable")

    result = await execute_read_only_tool(
        "summarize_document", arguments={},
        executor=intermittent,
        policy=ToolPolicy(timeout_seconds=0.03, max_retries=0, cpu_inference=True),
    )
    assert starts == 1
    assert result.event["attempts"] == 1
    assert result.event["error_type"] == "ConnectError"
    assert result.result["sources"] == []


@pytest.mark.asyncio
async def test_configured_timeout_is_used_without_changing_default_policy(monkeypatch):
    monkeypatch.setattr(
        config, "get_settings",
        lambda: SimpleNamespace(rag_cpu_timeout_seconds=520.0),
    )

    async def successful(name, *, arguments):
        return {"tool": name, "status": "answered"}

    result = await execute_read_only_tool(
        "search_documents", arguments={}, executor=successful,
    )
    assert result.event["timeout_seconds"] == 520
    assert result.event["attempts"] == 1
    assert result.event["status"] == "ok"
    assert READ_ONLY_POLICIES["search_documents"].timeout_seconds == 420


def test_live_diagnostics_redact_document_and_model_text():
    diagnostic = live_failure_diagnostic({
        "status": "tool_unavailable",
        "trace_id": "some-trace",
        "answer": "PRIVATE DOCUMENT BODY",
        "sources": [{"evidence": "CONFIDENTIAL SOURCE"}],
        "tool_events": [{
            "tool": "search_documents", "status": "fallback",
            "attempts": 1, "timeout_seconds": 420,
            "duration_ms": 420001, "error_type": "TimeoutError",
            "raw_request": "RAW USER QUESTION",
        }],
    }, llm_calls=0)
    assert diagnostic["llm_calls"] == 0
    assert diagnostic["tool_events"][0]["attempts"] == 1
    assert "PRIVATE DOCUMENT BODY" not in str(diagnostic)
    assert "CONFIDENTIAL SOURCE" not in str(diagnostic)
    assert "RAW USER QUESTION" not in str(diagnostic)


def test_rag_timeout_settings_are_bounded_and_overrideable():
    from app.core.config import Settings

    assert Settings(_env_file=None, rag_cpu_timeout_seconds=420).rag_cpu_timeout_seconds == 420
    assert Settings(_env_file=None, rag_cpu_timeout_seconds=540).rag_cpu_timeout_seconds == 540
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_cpu_timeout_seconds=299)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, rag_cpu_timeout_seconds=601)


@pytest.mark.asyncio
async def test_rag_disallows_old_90_second_retry_policy():
    async def must_not_call(name, *, arguments):
        raise AssertionError("Invalid policy must fail before executing the tool")

    with pytest.raises(ValueError, match="must not restart"):
        await execute_read_only_tool(
            "search_documents", arguments={}, executor=must_not_call,
            policy=ToolPolicy(timeout_seconds=90, max_retries=2),
        )
