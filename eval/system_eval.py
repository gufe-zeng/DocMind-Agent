"""M7c evaluation aggregations: measured wall-clock times and observed tool events.

Metrics come from the evaluation caller and the existing M6a tool_events.
No new public API, Prometheus series, or production tracing is introduced.
Absent token/timing data is None, not a fabricated zero.
"""
from dataclasses import dataclass
import math
from statistics import mean, median
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentTiming:
    case_id: str
    latency_ms: float
    http_status: int | None
    agent_status: str | None
    tools_called: tuple[str, ...]
    tool_events: tuple[dict[str, Any], ...]
    verified_no_llm: bool = False


@dataclass(frozen=True, slots=True)
class LiveLLMProbe:
    latency_ms: float
    calls: int
    status: str
    prompt_tokens: int | None
    completion_tokens: int | None


def _nonnegative(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0
    )


def latency_summary(values: list[float]) -> dict | None:
    """p95 uses nearest-rank, so tiny samples should not be generalized."""
    if not values:
        return None
    if any(not _nonnegative(value) for value in values):
        raise ValueError("Latency samples must be finite and nonnegative.")
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return {
        "samples": len(values),
        "mean": round(mean(values), 2),
        "p50": round(median(values), 2),
        "p95": round(ordered[index], 2),
        "min": round(ordered[0], 2),
        "max": round(ordered[-1], 2),
        "unit": "ms",
    }


def evaluate_system(
    samples: list[AgentTiming],
    *,
    standalone_retrieval_ms: float | None = None,
    standalone_rerank_ms: float | None = None,
    live_llm_probe: LiveLLMProbe | None = None,
) -> dict:
    """Aggregate observables without claiming uninstrumented phase timings.

    HTTP Agent timings are not the sum of the separately sampled retrieval
    and reranker calls. Tool event durations include retries/backoff when
    present; they are not exclusive CPU time.
    """
    if not samples or len({s.case_id for s in samples}) != len(samples):
        raise ValueError("System evaluation needs unique nonempty case IDs.")
    if any(not s.case_id or not _nonnegative(s.latency_ms) for s in samples):
        raise ValueError("Invalid case IDs or request latencies.")
    for value in (standalone_retrieval_ms, standalone_rerank_ms):
        if value is not None and not _nonnegative(value):
            raise ValueError("Standalone stage latency must be nonnegative/finite.")
    if live_llm_probe is not None:
        if (
            not _nonnegative(live_llm_probe.latency_ms)
            or isinstance(live_llm_probe.calls, bool)
            or not isinstance(live_llm_probe.calls, int)
            or live_llm_probe.calls < 0
        ):
            raise ValueError("Invalid LLM probe timing or call count.")
        for value in (live_llm_probe.prompt_tokens, live_llm_probe.completion_tokens):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError("Token counts must be nonnegative integers or None.")

    tool_durations = []
    tool_calls = 0
    missing_events = 0
    per_tool: dict[str, list[float]] = {}
    for sample in samples:
        for index, name in enumerate(sample.tools_called):
            tool_calls += 1
            event = (
                sample.tool_events[index]
                if index < len(sample.tool_events) else None
            )
            if (
                not isinstance(event, dict)
                or event.get("tool") != name
                or not _nonnegative(event.get("duration_ms"))
                or event.get("status") not in ("ok", "fallback")
            ):
                missing_events += 1
                continue
            duration = float(event["duration_ms"])
            tool_durations.append(duration)
            per_tool.setdefault(name, []).append(duration)
        if len(sample.tool_events) > len(sample.tools_called):
            raise ValueError("More tool events than reported tool calls.")

    no_model_workload = all(s.verified_no_llm for s in samples)
    llm = {
        "agent_requests_verified_no_llm": sum(s.verified_no_llm for s in samples),
        "agent_request_llm_calls": 0 if no_model_workload else None,
        "agent_request_prompt_tokens": 0 if no_model_workload else None,
        "agent_request_completion_tokens": 0 if no_model_workload else None,
        "live_rag_probe": None,
    }
    if live_llm_probe is not None:
        llm["live_rag_probe"] = {
            "latency_ms": round(live_llm_probe.latency_ms, 2),
            "llm_calls": live_llm_probe.calls,
            "status": live_llm_probe.status,
            "prompt_tokens": live_llm_probe.prompt_tokens,
            "completion_tokens": live_llm_probe.completion_tokens,
            "tokens_measured": (
                live_llm_probe.prompt_tokens is not None
                and live_llm_probe.completion_tokens is not None
            ),
        }

    succeeded = sum(
        s.http_status == 200 and s.agent_status == "answered"
        for s in samples
    )
    return {
        "agent_requests": len(samples),
        "agent_http_answered": succeeded,
        "agent_failure_count": len(samples) - succeeded,
        "agent_e2e_latency": latency_summary([s.latency_ms for s in samples]),
        "read_only_tool_calls": tool_calls,
        "tool_events_missing_or_invalid": missing_events,
        "tool_event_coverage": (
            round((tool_calls - missing_events) / tool_calls, 4)
            if tool_calls else None
        ),
        "tool_latency": latency_summary(tool_durations),
        "tool_latency_by_name": {
            tool: latency_summary(values)
            for tool, values in sorted(per_tool.items())
        },
        "standalone_retrieval_latency_ms": (
            round(standalone_retrieval_ms, 2)
            if standalone_retrieval_ms is not None else None
        ),
        "standalone_rerank_latency_ms": (
            round(standalone_rerank_ms, 2)
            if standalone_rerank_ms is not None else None
        ),
        "standalone_stage_scope": (
            "direct in-container operations; not attributed to Agent HTTP latency"
        ),
        "llm_usage": llm,
        "evaluation_scope": "synthetic serial smoke; not a concurrency benchmark",
    }
