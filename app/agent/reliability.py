"""M6a read-only Tool Runtime: deadline, at most two retries, safe fallback.

Failures are explicitly classified. Timeouts / transient transport problems
may be retried; invalid parameters, incorrect MCP source data, and software
defects must not be hidden by a plausible answer or retried indefinitely.
Write tools are intentionally excluded; M6b adds approval-protected writes.

Cancellation at a Python coroutine boundary does not forcibly terminate
threads spawned by CPU inference or network requests already in progress.
This is a bounded local-demo executor, not exactly-once distributed execution.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from time import perf_counter
from typing import Any

import asyncpg
import httpx
from pydantic import ValidationError


@dataclass(frozen=True)
class ToolPolicy:
    timeout_seconds: float
    max_retries: int = 2
    backoff_seconds: float = 0.1
    cpu_inference: bool = False

    def __post_init__(self) -> None:
        # CPU ONNX inference may continue running inside asyncio.to_thread
        # after wait_for cancels its coroutine. Give it a longer, explicit
        # budget, but never retry the non-cancellable computation.
        limit = 600 if self.cpu_inference else 180
        if not (0 < self.timeout_seconds <= limit):
            raise ValueError(f"Tool timeout must be within (0, {limit}] seconds.")
        if self.cpu_inference and self.max_retries != 0:
            raise ValueError("CPU inference policies must not restart a cancelled worker.")
        if not (0 <= self.max_retries <= 2):
            raise ValueError("Maximum retry count is capped at two.")
        if not (0 <= self.backoff_seconds <= 5):
            raise ValueError("Invalid retry backoff.")


CPU_RAG_TOOLS = frozenset({"search_documents", "summarize_document"})


READ_ONLY_POLICIES: dict[str, ToolPolicy] = {
    "query_document_metadata": ToolPolicy(timeout_seconds=15),
    "search_documents": ToolPolicy(timeout_seconds=420, max_retries=0, cpu_inference=True),
    "extract_entities": ToolPolicy(timeout_seconds=45),
    "summarize_document": ToolPolicy(timeout_seconds=420, max_retries=0, cpu_inference=True),
    "mcp_get_document": ToolPolicy(timeout_seconds=40),
    "mcp_get_document_page": ToolPolicy(timeout_seconds=60),
    "mcp_find_clause": ToolPolicy(timeout_seconds=60),
    "mcp_search_documents": ToolPolicy(timeout_seconds=90),
}


@dataclass(frozen=True)
class ToolExecution:
    result: dict[str, Any]
    event: dict[str, Any]


def retryable_error(exc: Exception) -> bool:
    """Only transient transport/connection/timeouts can trigger retries."""
    if isinstance(exc, (TimeoutError, ConnectionError, httpx.TransportError,
                        asyncpg.PostgresConnectionError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exc, ExceptionGroup):
        return bool(exc.exceptions) and all(
            isinstance(item, Exception) and retryable_error(item)
            for item in exc.exceptions
        )
    cause = exc.__cause__
    return isinstance(cause, Exception) and retryable_error(cause)


ToolExecutor = Callable[..., Awaitable[dict[str, Any]]]


async def execute_read_only_tool(
    name: str,
    *,
    arguments: dict[str, Any],
    executor: ToolExecutor,
    policy: ToolPolicy | None = None,
) -> ToolExecution:
    """Call exactly one allowlisted, read-only tool.

    When retryable errors persist, return a clearly marked non-factual
    fallback with no citations. Never convert argument/contract errors into
    silent success and never retry writes.
    """
    if name not in READ_ONLY_POLICIES:
        raise ValueError(f"No read-only reliability policy for tool: {name}")
    active = policy or READ_ONLY_POLICIES[name]
    if name in CPU_RAG_TOOLS:
        if active.max_retries != 0:
            raise ValueError("RAG tools must not restart non-cancellable CPU inference.")
        if policy is None:
            # Runtime-configurable without reinstalling/rebuilding the API:
            # recreate only the API container after updating Compose env.
            from app.core.config import get_settings
            active = replace(
                active, timeout_seconds=get_settings().rag_cpu_timeout_seconds,
            )
    started = perf_counter()

    for attempt in range(active.max_retries + 1):
        try:
            result = await asyncio.wait_for(
                executor(name, arguments=arguments),
                timeout=active.timeout_seconds,
            )
        except (ValueError, ValidationError):
            raise
        except Exception as exc:
            if not retryable_error(exc):
                raise
            if attempt < active.max_retries:
                await asyncio.sleep(active.backoff_seconds * (attempt + 1))
                continue

            event = {
                "tool": name,
                "status": "fallback",
                "attempts": attempt + 1,
                "retries": attempt,
                "timeout_seconds": active.timeout_seconds,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "error_type": type(exc).__name__,
            }
            fallback = {
                "tool": name,
                "status": "tool_unavailable",
                "answer": "当前文档工具暂不可用，已停止重试；无法确认相应文档信息。",
                "sources": [],
                "runtime": event,
            }
            return ToolExecution(result=fallback, event=event)

        if not isinstance(result, dict):
            raise TypeError(f"Tool {name} must return a dictionary.")
        if result.get("tool") != name:
            raise RuntimeError(f"Tool identity mismatch for {name}.")

        event = {
            "tool": name,
            "status": "ok",
            "attempts": attempt + 1,
            "retries": attempt,
            "timeout_seconds": active.timeout_seconds,
            "duration_ms": round((perf_counter() - started) * 1000, 2),
        }
        return ToolExecution(result={**result, "runtime": event}, event=event)

    raise AssertionError("Tool retry policy iteration cannot be empty.")
