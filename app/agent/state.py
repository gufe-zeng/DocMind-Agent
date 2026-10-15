"""M3a: serializable state contract for the LangGraph runtime.

M4 adds session memory and durable checkpointers. M3a is deliberately
stateless between requests even when callers provide a session_id.
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str
    document_id: str | None
    query: str
    messages: list[Any]

    intent: str
    plan: list[str]
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
