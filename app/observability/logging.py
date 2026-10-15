"""M8 privacy-preserving structured Agent lifecycle logs.

Request text, document passages, user IDs, filenames, and secrets are never
written by this logger; only fixed control-plane metadata is logged.
"""
import json
import logging
from typing import Any


logger = logging.getLogger("docmind.agent.trace")


def log_trace_summary(trace: Any, *, persisted: bool) -> None:
    logger.info(
        "agent_trace %s",
        json.dumps({
            "trace_id": str(trace.trace_id),
            "request_id": str(trace.request_id),
            "operation": trace.operation,
            "status": trace.status,
            "http_status": trace.http_status,
            "duration_ms": trace.duration_ms,
            "node_count": len(trace.node_events),
            "tool_count": len(trace.tools_called),
            "llm_calls": trace.llm_calls,
            "persisted": persisted,
        }, separators=(",", ":"), sort_keys=True),
    )
