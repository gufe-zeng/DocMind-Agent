from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    session_id: str
    user_id: str
    query: str
    messages: list[Any]

    intent: str
    plan: list[str]

    retrieved_docs: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    entities: list[dict[str, Any]]

    current_step: int
    retry_count: int

    approval_required: bool
    final_answer: str
