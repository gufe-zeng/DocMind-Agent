"""M8: bounded-label Prometheus observations for the Agent and its tools.

Never put request/session/trace IDs, raw user text, filenames, or exception
messages in metric labels. This module has no dependency on FastAPI.
"""
from prometheus_client import Counter, Histogram


AGENT_REQUESTS = Counter(
    "agent_requests", "Agent HTTP requests, including approval decisions.", ["operation"]
)
AGENT_SUCCESS = Counter(
    "agent_success", "Agent requests with a successful terminal or pending outcome.", ["operation"]
)
AGENT_FAILURES = Counter(
    "agent_failures", "Agent HTTP failures and unsuccessful terminal outcomes.", ["operation"]
)
AGENT_STEPS = Histogram(
    "agent_steps", "Executed LangGraph tool steps per Agent request.",
    buckets=(0, 1, 2, 3, 4, 5, 6, 8, 10),
)
AGENT_E2E = Histogram(
    "agent_e2e_latency_seconds", "Agent handler latency excluding trace persistence.",
    ["operation"], buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 180),
)
TOOL_CALLS = Counter(
    "tool_calls", "Read-only Agent tool executions.", ["tool"]
)
TOOL_FAILURES = Counter(
    "tool_failures", "Read-only Agent tool fallbacks or missing execution events.", ["tool"]
)
TOOL_LATENCY = Histogram(
    "tool_latency_seconds", "Tool execution wall clock including retries.", ["tool"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 90, 180),
)
RAG_LATENCY = Histogram(
    "rag_latency_seconds", "Complete evidence-grounded RAG pipeline seconds.",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 90, 180, 360),
)
RETRIEVAL_LATENCY = Histogram(
    "retrieval_latency_seconds", "Hybrid Dense/BM25/RRF retrieval seconds.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 90),
)
RERANK_LATENCY = Histogram(
    "rerank_latency_seconds", "BGE reranker wall-clock seconds.",
    buckets=(0.025, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 90, 180, 360),
)
LLM_CALLS = Counter("llm_calls", "Attempted OpenAI-compatible chat calls.")
LLM_FAILURES = Counter("llm_failures", "LLM calls without a valid completion.")
LLM_PROMPT_TOKENS = Counter("llm_prompt_tokens", "Reported prompt tokens.")
LLM_COMPLETION_TOKENS = Counter("llm_completion_tokens", "Reported completion tokens.")
TRACE_STORE_FAILURES = Counter(
    "agent_trace_store_failures", "Trace writes that could not reach PostgreSQL."
)


_ALLOWED_TOOL_NAMES = frozenset({
    "query_document_metadata", "search_documents", "extract_entities",
    "summarize_document", "mcp_get_document", "mcp_get_document_page",
    "mcp_find_clause", "mcp_search_documents", "save_review_note",
})


def safe_tool_name(name: object) -> str:
    return name if isinstance(name, str) and name in _ALLOWED_TOOL_NAMES else "other"


def observe_request(
    operation: str, *, status: str, http_status: int, seconds: float,
    steps: int | None, tool_events: list[dict], tools_called: list[str],
) -> None:
    """Emit counters after a request has completed; only fixed low-cardinality labels."""
    if operation not in ("chat", "approval"):
        raise ValueError("Unregistered Agent operation.")
    AGENT_REQUESTS.labels(operation=operation).inc()
    if http_status == 200 and status in {
        "answered", "no_evidence", "insufficient_evidence", "approved",
        "rejected", "approval_required", "memory_saved",
    }:
        AGENT_SUCCESS.labels(operation=operation).inc()
    else:
        AGENT_FAILURES.labels(operation=operation).inc()
    AGENT_E2E.labels(operation=operation).observe(max(seconds, 0.0))
    if steps is not None and isinstance(steps, int) and not isinstance(steps, bool) and steps >= 0:
        AGENT_STEPS.observe(steps)
    # Explicitly count missing records as failures; no arbitrary error strings as labels.
    for index, tool in enumerate(tools_called):
        label = safe_tool_name(tool)
        TOOL_CALLS.labels(tool=label).inc()
        event = tool_events[index] if index < len(tool_events) else None
        if not isinstance(event, dict) or event.get("tool") != tool:
            TOOL_FAILURES.labels(tool=label).inc()
            continue
        duration = event.get("duration_ms")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
            TOOL_LATENCY.labels(tool=label).observe(float(duration) / 1000)
        if event.get("status") != "ok":
            TOOL_FAILURES.labels(tool=label).inc()


def observe_llm_start() -> None:
    LLM_CALLS.inc()


def observe_llm_failure() -> None:
    LLM_FAILURES.inc()


def observe_llm_usage(prompt_tokens: int | None, completion_tokens: int | None) -> None:
    if prompt_tokens is not None:
        LLM_PROMPT_TOKENS.inc(prompt_tokens)
    if completion_tokens is not None:
        LLM_COMPLETION_TOKENS.inc(completion_tokens)

# Create zero-valued bounded series so Grafana can display no-failure baselines.
for _operation in ("chat", "approval"):
    AGENT_REQUESTS.labels(operation=_operation)
    AGENT_SUCCESS.labels(operation=_operation)
    AGENT_FAILURES.labels(operation=_operation)
    AGENT_E2E.labels(operation=_operation)
