"""M7b: auditable Agent metrics over independently specified task outcomes.

A correct tool route is NOT sufficient for task success. Task success checks
status, predeclared literal facts, entity values, source scope, and citations.
These are deterministic fixture assertions, not a semantic LLM judge.
"""
from dataclasses import dataclass
from statistics import mean
from typing import Any
import re


CITATION_RE = re.compile(r"\[S\d+\]")
RUNTIME_FAILURE_STATUSES = frozenset({
    "tool_unavailable", "partial", "citation_unverified", "step_limit",
    "failed", "error", "unknown",
})


@dataclass(frozen=True, slots=True)
class AgentEvalCase:
    case_id: str
    expected_tools: tuple[str, ...]
    expected_status: str = "answered"
    expected_mcp_tools: tuple[str, ...] = ()
    answer_contains: tuple[str, ...] = ()
    expected_entities: tuple[tuple[str, str], ...] = ()
    expected_document_id: str | None = None
    expected_page: int | None = None
    require_sources: bool = False
    max_steps: int = 8


def _names(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(x, str) for x in value):
        return ()
    return tuple(value)


def _source_contract(case: AgentEvalCase, payload: dict) -> bool:
    sources = payload.get("sources")
    answer = payload.get("answer")
    if not isinstance(sources, list) or not isinstance(answer, str):
        return False
    if any(not isinstance(s, dict) for s in sources):
        return False
    source_ids = [s.get("id") for s in sources]
    if (
        any(not isinstance(sid, str) or not re.fullmatch(r"S\d+", sid) for sid in source_ids)
        or len(source_ids) != len(set(source_ids))
    ):
        return False
    cited = set(CITATION_RE.findall(answer))
    allowed = {"[" + sid + "]" for sid in source_ids}
    if not cited.issubset(allowed):
        return False
    if case.require_sources and (not sources or not cited):
        return False

    for source in sources:
        if not all(isinstance(source.get(k), str) and source[k] for k in (
            "document_id", "chunk_id", "filename", "evidence",
        )):
            return False
        if case.expected_document_id and source["document_id"] != case.expected_document_id:
            return False
        if case.expected_page is not None and source.get("page") != case.expected_page:
            return False

    entities = payload.get("entities")
    if not isinstance(entities, list) or any(not isinstance(e, dict) for e in entities):
        return False
    by_field = {}
    source_by_id = {str(sid): source for sid, source in zip(source_ids, sources)}
    for entity in entities:
        field = entity.get("field")
        source = source_by_id.get(entity.get("source_id"))
        if not isinstance(field, str) or source is None:
            return False
        if entity.get("chunk_id") != source.get("chunk_id"):
            return False
        by_field[field] = entity.get("value")
    return all(by_field.get(field) == value for field, value in case.expected_entities)


def _task_success(case: AgentEvalCase, payload: dict | None) -> bool:
    if payload is None or payload.get("status") != case.expected_status:
        return False
    answer = payload.get("answer")
    if not isinstance(answer, str) or any(
        required not in answer for required in case.answer_contains
    ):
        return False
    steps = payload.get("steps")
    if isinstance(steps, bool) or not isinstance(steps, int) or not (0 <= steps <= case.max_steps):
        return False
    tools = _names(payload.get("tools_called"))
    if steps != len(tools):
        return False
    return _source_contract(case, payload)


def evaluate_agent(
    cases: list[AgentEvalCase],
    responses: list[dict | None],
) -> dict:
    """Compute observable Agent metrics. None denotes HTTP/transport failure.

    - Task success: fixture status + content + evidence and step constraints;
      independent from expected tool choice.
    - Tool selection: exact SET match of executed tools, excluding duplicates.
    - Tool success: read-only tool events with status=ok / actual called tools.
    - Failure rate: transport errors and explicit runtime failure statuses,
      not the complement of task success.
    - Average steps: among responses with valid nonnegative step counts.
    """
    if not cases or len(cases) != len(responses):
        raise ValueError("Need aligned nonempty Agent cases and responses.")
    if any(not c.case_id or not c.expected_tools or c.max_steps <= 0 for c in cases):
        raise ValueError("Each case needs an ID, expected tools and positive step bound.")
    if len({c.case_id for c in cases}) != len(cases):
        raise ValueError("Duplicate case IDs.")
    if any(r is not None and not isinstance(r, dict) for r in responses):
        raise ValueError("Responses must be dictionaries or None.")

    task_count = 0
    selection_count = 0
    mcp_count = 0
    runtime_failures = 0
    event_count = 0
    event_ok_count = 0
    step_values: list[int] = []
    case_results: list[dict] = []

    for case, response in zip(cases, responses):
        tools = _names(response.get("tools_called")) if response else ()
        mcp = _names(response.get("mcp_tools_called")) if response else ()
        chosen = len(tools) == len(set(tools)) and set(tools) == set(case.expected_tools)
        mcp_chosen = mcp == case.expected_mcp_tools
        success = _task_success(case, response)
        runtime_failed = response is None or response.get("status") in RUNTIME_FAILURE_STATUSES
        if response is not None and not isinstance(response.get("status"), str):
            runtime_failed = True

        task_count += int(success)
        selection_count += int(chosen)
        mcp_count += int(mcp_chosen)
        runtime_failures += int(runtime_failed)

        if response is not None:
            steps = response.get("steps")
            if isinstance(steps, int) and not isinstance(steps, bool) and steps >= 0:
                step_values.append(steps)
            events = response.get("tool_events")
            events = events if isinstance(events, list) else []
            for index, name in enumerate(tools):
                event_count += 1
                event = events[index] if index < len(events) else None
                if (
                    isinstance(event, dict)
                    and event.get("tool") == name
                    and event.get("status") == "ok"
                    and isinstance(event.get("attempts"), int)
                    and 1 <= event["attempts"] <= 3
                ):
                    event_ok_count += 1

        case_results.append({
            "case_id": case.case_id,
            "task_success": success,
            "tool_selection_correct": chosen,
            "mcp_selection_correct": mcp_chosen,
            "runtime_failed": runtime_failed,
            "status": response.get("status") if response else "request_failed",
            "steps": response.get("steps") if response else None,
        })

    n = len(cases)
    return {
        "cases": n,
        "task_success_rate": task_count / n,
        "tool_selection_accuracy": selection_count / n,
        "mcp_tool_selection_accuracy": mcp_count / n,
        "tool_success_rate": event_ok_count / event_count if event_count else None,
        "evaluated_tool_calls": event_count,
        "average_agent_steps": mean(step_values) if step_values else None,
        "requests_with_steps": len(step_values),
        "failure_rate": runtime_failures / n,
        "evaluation_scope": "synthetic, rule/MCP-backed task assertions; no model judge",
        "case_results": case_results,
    }
