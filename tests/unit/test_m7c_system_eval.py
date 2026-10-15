"""M7c pure metric contract tests; no Docker or model required."""
import math

import pytest

from eval.system_eval import (
    AgentTiming, LiveLLMProbe, evaluate_system, latency_summary,
)


def sample(case_id="case-1", *, latency=12.0, status="answered", http=200,
           tool="mcp_find_clause", duration=5.0, verified=True):
    return AgentTiming(
        case_id=case_id,
        latency_ms=latency,
        http_status=http,
        agent_status=status,
        tools_called=(tool,),
        tool_events=({
            "tool": tool, "status": "ok", "attempts": 1,
            "retries": 0, "duration_ms": duration,
        },),
        verified_no_llm=verified,
    )


def test_request_tool_standalone_and_no_llm_counters():
    report = evaluate_system(
        [sample(), sample("case-2", latency=28.0, duration=9.0)],
        standalone_retrieval_ms=40.4,
        standalone_rerank_ms=23.1,
    )
    assert report["agent_requests"] == 2
    assert report["agent_http_answered"] == 2
    assert report["agent_e2e_latency"]["p50"] == 20
    assert report["agent_e2e_latency"]["p95"] == 28
    assert report["tool_latency"]["mean"] == 7
    assert report["tool_event_coverage"] == 1.0
    assert report["standalone_retrieval_latency_ms"] == 40.4
    assert report["standalone_rerank_latency_ms"] == 23.1
    assert report["llm_usage"]["agent_request_llm_calls"] == 0
    assert report["llm_usage"]["agent_request_prompt_tokens"] == 0
    assert report["llm_usage"]["live_rag_probe"] is None


def test_missing_events_are_not_reported_as_zero_duration():
    missing = AgentTiming(
        case_id="missing", latency_ms=1, http_status=200,
        agent_status="answered", tools_called=("mcp_find_clause",),
        tool_events=(), verified_no_llm=True,
    )
    report = evaluate_system([missing])
    assert report["tool_latency"] is None
    assert report["tool_event_coverage"] == 0
    assert report["tool_events_missing_or_invalid"] == 1
    assert report["read_only_tool_calls"] == 1


def test_unknown_llm_usage_stays_null_not_zero():
    unknown = sample(verified=False)
    report = evaluate_system([unknown])
    assert report["llm_usage"]["agent_request_llm_calls"] is None
    assert report["llm_usage"]["agent_request_prompt_tokens"] is None
    assert report["standalone_rerank_latency_ms"] is None


def test_live_probe_real_counts_and_unavailable_usage():
    probe = LiveLLMProbe(
        latency_ms=130, calls=1, status="answered",
        prompt_tokens=74, completion_tokens=21,
    )
    report = evaluate_system([sample()], live_llm_probe=probe)
    live = report["llm_usage"]["live_rag_probe"]
    assert live["llm_calls"] == 1
    assert live["tokens_measured"]
    assert (live["prompt_tokens"], live["completion_tokens"]) == (74, 21)

    absent = evaluate_system([sample()], live_llm_probe=LiveLLMProbe(
        latency_ms=100, calls=1, status="answered",
        prompt_tokens=None, completion_tokens=None,
    ))["llm_usage"]["live_rag_probe"]
    assert absent["tokens_measured"] is False
    assert absent["prompt_tokens"] is None


def test_failure_rate_counts_http_errors_and_declared_agent_failures():
    failed = AgentTiming(
        case_id="503", latency_ms=16, http_status=503,
        agent_status=None, tools_called=(), tool_events=(),
    )
    partial = sample("partial", status="partial")
    report = evaluate_system([failed, partial])
    assert report["agent_failure_count"] == 2
    assert report["agent_http_answered"] == 0
    assert report["agent_e2e_latency"]["samples"] == 2


@pytest.mark.parametrize("invalid", [-1, math.nan, math.inf, True])
def test_invalid_latency_is_rejected(invalid):
    with pytest.raises(ValueError):
        evaluate_system([sample(latency=invalid)])
    with pytest.raises(ValueError):
        latency_summary([invalid])


def test_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        evaluate_system([sample(), sample()])
    with pytest.raises(ValueError):
        evaluate_system([])


def test_wrong_tool_event_is_not_silently_timed():
    original = sample()
    wrong = AgentTiming(
        case_id="wrong", latency_ms=original.latency_ms, http_status=200,
        agent_status="answered", tools_called=original.tools_called,
        tool_events=({"tool": "other", "status": "ok", "duration_ms": 5},),
        verified_no_llm=True,
    )
    score = evaluate_system([wrong])
    assert score["tool_latency"] is None
    assert score["tool_events_missing_or_invalid"] == 1


def test_more_events_than_tools_rejected():
    with pytest.raises(ValueError):
        evaluate_system([AgentTiming(
            case_id="extra", latency_ms=1, http_status=200,
            agent_status="answered", tools_called=(),
            tool_events=({"tool": "unexpected", "duration_ms": 1},),
        )])
