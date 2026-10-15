"""M3b LangGraph route → decide → call tool → synthesize.

A separate source namespace is allocated per final answer so two independent
tools cannot both return ambiguous [S1] references to different chunks.
"""

import re
from typing import Any

from app.agent.router import plan_tools
from app.agent.state import AgentState
from app.agent.reliability import execute_read_only_tool
from app.tools.registry import invoke_tool
from app.tools.mcp_bridge import clause_keyword_from_query, page_number_from_query


MAX_AGENT_TOOL_STEPS = 8
_CITATION_PATTERN = re.compile(r"\[S(\d+)\]")


async def route_node(state: AgentState) -> dict[str, Any]:
    decision = await plan_tools(state["query"], state.get("document_id"))
    plan = decision.tools
    return {
        "intent": "multi_tool" if len(plan) > 1 else plan[0],
        "plan": plan,
        "plan_source": decision.source,
        "planner_fallback_reason": decision.reason,
        "tool_results": [],
        "tools_called": [],
        "reliability_events": [],
        "retry_count": 0,
        "current_step": 0,
        "sources": [],
        "entities": [],
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


async def _resume_protected_review_note(state: AgentState) -> dict[str, Any]:
    """The graph cannot execute save_review_note before Human Approval.

    An official LangGraph interrupt persists the paused call_tool node.
    On resume the decision must *also* be persisted in PostgreSQL. The
    only side effect is the transactional and idempotent approved write.
    """
    from uuid import UUID

    from langgraph.types import interrupt

    from app.approvals.storage import get_approval, execute_approved_review_note

    raw_id = state.get("approval_id")
    raw_user = state.get("user_id")
    raw_session = state.get("session_id")
    if not raw_id or not raw_user or not raw_session or not state.get("document_id"):
        raise ValueError("Protected write requires a persisted approval and scoped identity.")

    resumed = interrupt({
        "approval_id": raw_id,
        "tool": "save_review_note",
        "message": "等待人工审批；此时没有执行写入。",
    })
    if (
        not isinstance(resumed, dict)
        or resumed.get("approval_id") != raw_id
        or resumed.get("decision") not in ("approve", "reject")
    ):
        raise ValueError("Invalid LangGraph Human Approval resume payload.")

    approval = await get_approval(UUID(raw_id))
    if approval is None:
        raise RuntimeError("Resumed approval record not found.")
    if (
        str(approval["session_id"]) != raw_session
        or str(approval["user_id"]) != raw_user
        or str(approval["document_id"]) != state["document_id"]
    ):
        raise RuntimeError("Approval scope mismatch during graph resume.")

    if resumed["decision"] == "approve":
        if approval["status"] != "approved":
            raise RuntimeError("A persisted approve decision is required.")
        saved = await execute_approved_review_note(
            UUID(raw_id), session_id=UUID(raw_session), user_id=UUID(raw_user)
        )
        result = {
            "tool": "save_review_note",
            "status": "approved",
            "answer": "审核备注已获批准并保存。",
            "approval_id": raw_id,
            "review_note_id": saved["review_note_id"],
            "sources": [],
        }
    else:
        if approval["status"] != "rejected":
            raise RuntimeError("A persisted reject decision is required.")
        result = {
            "tool": "save_review_note",
            "status": "rejected",
            "answer": "审核备注已被拒绝，未执行写入。",
            "approval_id": raw_id,
            "review_note_id": None,
            "sources": [],
        }
    return {
        "tool_results": [*state.get("tool_results", []), result],
        "tools_called": [*state.get("tools_called", []), "save_review_note"],
        "current_step": state.get("current_step", 0) + 1,
        "next_tool": None,
        "approval_required": False,
    }


async def call_tool_node(state: AgentState) -> dict[str, Any]:
    name = state.get("next_tool")
    if name is None:
        raise RuntimeError("Tool node called without a selected tool.")
    if name == "save_review_note":
        return await _resume_protected_review_note(state)

    arguments: dict[str, Any] = {"document_id": state.get("document_id")}
    if name in ("search_documents", "extract_entities", "summarize_document"):
        arguments["query"] = state["query"]
    if name in ("search_documents", "summarize_document") and state.get("format_hint"):
        arguments["format_hint"] = state["format_hint"]

    if name == "mcp_find_clause":
        arguments["keyword"] = clause_keyword_from_query(state["query"])
    elif name == "mcp_get_document_page":
        arguments["page"] = page_number_from_query(state["query"])
    elif name == "mcp_search_documents":
        # The server searches original question text; it is source-grounded.
        arguments["query"] = state["query"]
        arguments["limit"] = 5

    execution = await execute_read_only_tool(
        name, arguments=arguments, executor=invoke_tool,
    )
    return {
        "tool_results": [*state.get("tool_results", []), execution.result],
        "reliability_events": [
            *state.get("reliability_events", []), execution.event,
        ],
        "retry_count": state.get("retry_count", 0) + execution.event["retries"],
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


def _relabel_tool_result(
    result: dict[str, Any],
    next_source_id: int,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], int, bool]:
    """Rewrite local source IDs to final-response global source IDs."""
    source_map: dict[str, str] = {}
    relabelled_sources: list[dict[str, Any]] = []
    for source in result.get("sources", []):
        original = str(source["id"])
        # Within a single tool, duplicated IDs are not valid source metadata.
        if original in source_map:
            raise ValueError(f"Duplicate source ID from {result['tool']}: {original}")
        replacement = f"S{next_source_id}"
        next_source_id += 1
        source_map[original] = replacement
        relabelled_sources.append({**source, "id": replacement})

    unknown_citation = False

    def replace_match(match: re.Match[str]) -> str:
        nonlocal unknown_citation
        old_id = f"S{match.group(1)}"
        new_id = source_map.get(old_id)
        if new_id is None:
            unknown_citation = True
            return "[INVALID_SOURCE]"
        return f"[{new_id}]"

    answer = _CITATION_PATTERN.sub(replace_match, str(result.get("answer", "")))

    entities: list[dict[str, Any]] = []
    for entity in result.get("entities", []):
        old = entity.get("source_id")
        if old not in source_map:
            unknown_citation = True
            continue
        entities.append({**entity, "source_id": source_map[old]})

    return answer, relabelled_sources, entities, next_source_id, unknown_citation


async def synthesize_node(state: AgentState) -> dict[str, Any]:
    replies: list[str] = []
    sources: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    step_statuses: list[str] = []
    next_source_id = 1

    for result in state.get("tool_results", []):
        tool_status = str(result.get("status", "answered"))
        step_statuses.append(tool_status)

        if result.get("tool") == "query_document_metadata" and tool_status != "tool_unavailable":
            replies.append(_summarize_metadata(result))
            continue

        answer, tool_sources, tool_entities, next_source_id, invalid = _relabel_tool_result(
            result, next_source_id
        )
        sources.extend(tool_sources)
        entities.extend(tool_entities)
        replies.append(
            "该工具的引用编号无法验证，已隐藏原始结论。"
            if invalid else answer
        )
        if invalid:
            step_statuses[-1] = "citation_unverified"

    if not replies:
        status = state.get("status", "no_evidence")
        return {
            "final_answer": (
                "执行步数达到上限，请缩小任务范围。"
                if status == "step_limit"
                else "当前没有可以使用的工具结果。"
            ),
            "status": status,
            "sources": sources,
            "entities": entities,
        }

    if state.get("status") == "step_limit":
        status = "step_limit"
    elif len(step_statuses) == 1 and step_statuses[0] in ("approved", "rejected"):
        status = step_statuses[0]
    elif "citation_unverified" in step_statuses:
        status = "citation_unverified"
    elif step_statuses and all(item == "tool_unavailable" for item in step_statuses):
        status = "tool_unavailable"
    elif all(item == "no_evidence" for item in step_statuses):
        status = "no_evidence"
    elif any(item not in ("answered",) for item in step_statuses):
        status = "partial"
    else:
        status = "answered"

    return {
        "final_answer": "\n\n".join(replies),
        "status": status,
        "sources": sources,
        "entities": entities,
    }
