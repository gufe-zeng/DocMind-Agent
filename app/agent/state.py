"""Serializable M3 state. Durable M4 memory/checkpoints come later."""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str
    document_id: str | None
    approval_id: str | None
    query: str
    messages: list[Any]
    format_hint: str | None

    intent: str
    plan: list[str]
    plan_source: str
    planner_fallback_reason: str | None
    next_tool: str | None

    retrieved_docs: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    entities: list[dict[str, Any]]

    current_step: int
    retry_count: int
    approval_required: bool
    final_answer: str
    status: str
    sources: list[dict[str, Any]]
    tools_called: list[str]
    reliability_events: list[dict[str, Any]]
