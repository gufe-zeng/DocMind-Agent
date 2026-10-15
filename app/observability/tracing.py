"""M8 request-local traces, LangGraph node spans and model usage.

Only UUIDs, allowlisted node/tool names, timestamps, bounded status tokens,
latencies and model token totals are retained. Document text, prompt text,
model replies and credentials are never stored in trace records.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import wraps
import logging
from time import perf_counter
from typing import Any, Callable
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.observability.metrics import (
    RAG_LATENCY, RETRIEVAL_LATENCY, RERANK_LATENCY,
    TRACE_STORE_FAILURES, observe_llm_start, observe_llm_failure,
    observe_llm_usage, observe_request, safe_tool_name,
)


logger = logging.getLogger(__name__)
_ALLOWED_NODES = frozenset({"route", "decide", "call_tool", "synthesize"})


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RequestTrace:
    trace_id: UUID = field(default_factory=uuid4)
    request_id: UUID = field(default_factory=uuid4)
    operation: str = "chat"
    session_id: UUID | None = None
    started_at: datetime = field(default_factory=_utc_now)
    started_counter: float = field(default_factory=perf_counter)
    status: str = "error"
    http_status: int = 500
    intent: str | None = None
    steps: int | None = None
    tools_called: list[str] = field(default_factory=list)
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    node_events: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: int = 0
    _llm_usage_count: int = 0
    _prompt_total: int = 0
    _completion_total: int = 0
    _prompt_complete: bool = True
    _completion_complete: bool = True
    duration_ms: float = 0.0
    ended_at: datetime | None = None
    error_type: str | None = None

    @property
    def prompt_tokens(self) -> int | None:
        return self._prompt_total if self._prompt_complete and self._llm_usage_count == self.llm_calls else None

    @property
    def completion_tokens(self) -> int | None:
        return self._completion_total if self._completion_complete and self._llm_usage_count == self.llm_calls else None


@dataclass(slots=True)
class NodeSpan:
    node: str
    started_at: datetime = field(default_factory=_utc_now)
    started_counter: float = field(default_factory=perf_counter)
    llm_calls: int = 0
    usage_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tokens_complete: bool = True


_current_trace: ContextVar[RequestTrace | None] = ContextVar("docmind_trace", default=None)
_current_node: ContextVar[NodeSpan | None] = ContextVar("docmind_node", default=None)


def current_trace() -> RequestTrace | None:
    return _current_trace.get()


@contextmanager
def node_span(node: str, *, tool: str | None = None):
    """Measure official graph nodes without changing checkpointer state."""
    trace = _current_trace.get()
    if trace is None:
        yield
        return
    if node not in _ALLOWED_NODES:
        raise ValueError("Unexpected LangGraph node for trace.")
    span = NodeSpan(node=node)
    token = _current_node.set(span)
    status = "ok"
    error_type = None
    try:
        yield
    except BaseException as exc:
        error_type = type(exc).__name__
        status = "interrupt" if error_type in ("GraphInterrupt", "GraphBubble") else "error"
        raise
    finally:
        ended = _utc_now()
        trace.node_events.append({
            "node": node,
            "start_time": span.started_at.isoformat(),
            "end_time": ended.isoformat(),
            "duration_ms": round((perf_counter() - span.started_counter) * 1000, 3),
            "status": status,
            "tool": safe_tool_name(tool) if node == "call_tool" else None,
            "llm_calls": span.llm_calls,
            "prompt_tokens": (
                span.prompt_tokens if span.tokens_complete and span.llm_calls == span.usage_calls else None
            ),
            "completion_tokens": (
                span.completion_tokens if span.tokens_complete and span.llm_calls == span.usage_calls else None
            ),
            "error_type": error_type if status == "error" else None,
        })
        _current_node.reset(token)


def observed_graph_node(node: str, func: Callable):
    @wraps(func)
    async def wrapper(state: dict):
        with node_span(node, tool=state.get("next_tool")):
            return await func(state)
    return wrapper


@contextmanager
def stage_timer(stage: str):
    """Stage metrics are in-process timings, never inferred from an Agent response."""
    histogram = {
        "rag": RAG_LATENCY,
        "retrieval": RETRIEVAL_LATENCY,
        "rerank": RERANK_LATENCY,
    }.get(stage)
    if histogram is None:
        raise ValueError("Invalid fixed observability stage.")
    begin = perf_counter()
    try:
        yield
    finally:
        histogram.observe(max(0.0, perf_counter() - begin))


def timed_rag(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        with stage_timer("rag"):
            return await func(*args, **kwargs)
    return wrapper


def timed_retrieval(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        with stage_timer("retrieval"):
            return await func(*args, **kwargs)
    return wrapper


def timed_rerank(func: Callable):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with stage_timer("rerank"):
            return func(*args, **kwargs)
    return wrapper


def record_llm_attempt() -> None:
    observe_llm_start()
    trace = _current_trace.get()
    node = _current_node.get()
    if trace is not None:
        trace.llm_calls += 1
    if node is not None:
        node.llm_calls += 1


def record_llm_failure() -> None:
    observe_llm_failure()


def record_llm_completion(prompt_tokens: int | None, completion_tokens: int | None) -> None:
    observe_llm_usage(prompt_tokens, completion_tokens)
    trace = _current_trace.get()
    node = _current_node.get()
    if trace is not None:
        trace._llm_usage_count += 1
        if prompt_tokens is None:
            trace._prompt_complete = False
        else:
            trace._prompt_total += prompt_tokens
        if completion_tokens is None:
            trace._completion_complete = False
        else:
            trace._completion_total += completion_tokens
    if node is not None:
        node.usage_calls += 1
        if prompt_tokens is None or completion_tokens is None:
            node.tokens_complete = False
        else:
            node.prompt_tokens += prompt_tokens
            node.completion_tokens += completion_tokens


def _copy_response_metadata(trace: RequestTrace, response: Any) -> None:
    trace.status = str(getattr(response, "status", "unknown"))
    session = getattr(response, "session_id", None)
    if isinstance(session, UUID):
        trace.session_id = session
    request_id = getattr(response, "request_id", None)
    if isinstance(request_id, UUID):
        trace.request_id = request_id
    trace.intent = getattr(response, "intent", None)
    trace.steps = getattr(response, "steps", None)
    trace.tools_called = list(getattr(response, "tools_called", []))
    trace.tool_events = [
        # M6a's allowlisted runtime fields, no source excerpts.
        {key: event[key] for key in (
            "tool", "status", "attempts", "retries",
            "timeout_seconds", "duration_ms", "error_type",
        ) if key in event}
        for event in getattr(response, "tool_events", [])
        if isinstance(event, dict)
    ]
    if hasattr(response, "trace_id"):
        response.trace_id = trace.trace_id
    if hasattr(response, "request_id") and getattr(response, "request_id") is None:
        response.request_id = trace.request_id


async def _finish_trace(trace: RequestTrace, http_request: Any) -> None:
    trace.duration_ms = round((perf_counter() - trace.started_counter) * 1000, 3)
    trace.ended_at = _utc_now()
    observe_request(
        trace.operation, status=trace.status, http_status=trace.http_status,
        seconds=trace.duration_ms / 1000, steps=trace.steps,
        tools_called=trace.tools_called, tool_events=trace.tool_events,
    )
    persisted = False
    try:
        pool = http_request.app.state.trace_pool
        from app.observability.storage import persist_trace
        await persist_trace(pool, trace)
        persisted = True
    except Exception:
        TRACE_STORE_FAILURES.inc()
        logger.exception(
            "Agent trace persistence failed: trace_id=%s operation=%s",
            trace.trace_id, trace.operation,
        )
    finally:
        from app.observability.logging import log_trace_summary
        log_trace_summary(trace, persisted=persisted)


def observed_endpoint(operation: str):
    """Wrap existing FastAPI endpoint without changing the frozen URL surface.

    FastAPI sees the original signature via functools.wraps. Each attempt is
    counted, including HTTPException responses. Pydantic body-validation 422
    is handled upstream and is outside this endpoint-level instrumentation.
    """
    if operation not in ("chat", "approval"):
        raise ValueError("Unexpected operation.")
    def decorate(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            http_request = kwargs["http_request"]
            body = kwargs.get("body") or kwargs.get("request")
            session = getattr(body, "session_id", None)
            trace = RequestTrace(
                operation=operation,
                session_id=session if isinstance(session, UUID) else None,
            )
            token = _current_trace.set(trace)
            try:
                response = await func(*args, **kwargs)
                trace.http_status = 200
                _copy_response_metadata(trace, response)
                return response
            except HTTPException as exc:
                trace.http_status = exc.status_code
                trace.status = "http_error"
                trace.error_type = type(exc).__name__
                raise
            except BaseException as exc:
                trace.http_status = 503 if isinstance(exc, Exception) else 500
                trace.status = "error"
                trace.error_type = type(exc).__name__
                raise
            finally:
                _current_trace.reset(token)
                await _finish_trace(trace, http_request)
        return wrapper
    return decorate
