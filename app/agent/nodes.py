"""M3a: explicit LangGraph route → decide → call tool → synthesize nodes.

Every Tool call is recorded in a serializable list; M4 adds durable state.
"""

from typing import Any

from app.agent.router import select_tool_plan
from app.agent.state import AgentState
from app.tools.registry import invoke_tool


MAX_AGENT_TOOL_STEPS = 8


async def route_node(state: AgentState) -> dict[str, Any]:
    plan = select_tool_plan(state["query"])
    return {
        "intent": "metadata_and_qa" if len(plan) > 1 else plan[0],
        "plan": plan,
        "tool_results": [],
        "tools_called": [],
        "current_step": 0,
        "sources": [],
    }


async def decide_node(state: AgentState) -> dict[str, Any]:
    step = state.get("current_step", 0)
    plan = state.get("plan", [])
    if step >= MAX_AGENT_TOOL_STEPS:
        return {"next_tool": None, "status": "step_limit"}
    if step >= len(plan):
        return {"next_tool": None}
    return {"next_tool": plan[step]}


def next_edge(state: AgentState) -> str:
    return "call_tool" if state.get("next_tool") else "synthesize"


async def call_tool_node(state: AgentState) -> dict[str, Any]:
    name = state.get("next_tool")
    if name is None:
        raise RuntimeError("Tool node called without a selected tool.")

    kwargs: dict[str, Any] = {"document_id": state.get("document_id")}
    if name == "search_documents":
        kwargs["query"] = state["query"]

    result = await invoke_tool(name, arguments=kwargs)
    return {
        "tool_results": [*state.get("tool_results", []), result],
        "tools_called": [*state.get("tools_called", []), name],
        "current_step": state.get("current_step", 0) + 1,
        "next_tool": None,
    }


def _summarize_metadata(result: dict[str, Any]) -> str:
    docs = result.get("documents") or []
    if not docs:
        return "当前范围内未找到已上传的文档。"
    items = [
        f"- {d['filename']}（{d['status']}，{d['chunk_count']} 个片段）"
        for d in docs
    ]
    return "查询到的文档：\n" + "\n".join(items)


async def synthesize_node(state: AgentState) -> dict[str, Any]:
    """Join approved tool outputs; don't fabricate facts or citation IDs."""
    replies: list[str] = []
    sources: list[dict[str, Any]] = []
    status = state.get("status", "answered")
    results = state.get("tool_results", [])
    for result in results:
        if result["tool"] == "search_documents":
            replies.append(str(result["answer"]))
            sources.extend(result.get("sources", []))
        elif result["tool"] == "query_document_metadata":
            replies.append(_summarize_metadata(result))

        if result.get("status") not in (None, "answered"):
            status = str(result["status"])

    if not replies:
        if status == "step_limit":
            return {
                "final_answer": "执行步数达到上限，请缩小任务范围。",
                "status": status,
                "sources": sources,
            }
        return {
            "final_answer": "当前没有可以使用的工具结果。",
            "status": "no_evidence",
            "sources": sources,
        }
    return {"final_answer": "\n\n".join(replies), "status": status, "sources": sources}
