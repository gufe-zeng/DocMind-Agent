"""M7b metric contract tests: no Docker, LLM or injected tool mocks."""
import pytest

from eval.agent_eval import AgentEvalCase, evaluate_agent


def result(*, tools=("extract_entities",), status="answered", answer="甲方：示例公司 [S1]",
           source_doc="doc-a", page=None, event_status="ok"):
    return {
        "status": status,
        "answer": answer,
        "tools_called": list(tools),
        "mcp_tools_called": [],
        "steps": len(tools),
        "sources": [{
            "id": "S1", "document_id": source_doc,
            "chunk_id": "chunk-1", "filename": "sample.txt",
            "page": page, "section": None, "evidence": "甲方：示例公司",
        }],
        "entities": [{
            "field": "甲方", "value": "示例公司",
            "source_id": "S1", "chunk_id": "chunk-1",
        }],
        "tool_events": [
            {"tool": name, "status": event_status, "attempts": 1}
            for name in tools
        ],
    }


def extraction_case():
    return AgentEvalCase(
        case_id="extract", expected_tools=("extract_entities",),
        expected_document_id="doc-a", require_sources=True,
        answer_contains=("示例公司",), expected_entities=(("甲方", "示例公司"),),
    )


def test_success_and_separate_tool_metrics():
    score = evaluate_agent([extraction_case()], [result()])
    assert score["task_success_rate"] == 1.0
    assert score["tool_selection_accuracy"] == 1.0
    assert score["mcp_tool_selection_accuracy"] == 1.0
    assert score["tool_success_rate"] == 1.0
    assert score["average_agent_steps"] == 1
    assert score["failure_rate"] == 0.0


def test_correct_fact_does_not_prove_tool_selection():
    other = result(tools=("mcp_find_clause",))
    score = evaluate_agent([extraction_case()], [other])
    assert score["task_success_rate"] == 1.0
    assert score["tool_selection_accuracy"] == 0.0
    assert score["tool_success_rate"] == 1.0


@pytest.mark.parametrize("change", [
    {"answer": "甲方：示例公司 [S99]"},
    {"answer": "甲方：示例公司"},
    {"source_doc": "wrong-doc"},
    {"page": 3},
])
def test_bad_provenance_or_missing_citation_is_task_failure(change):
    case = extraction_case()
    if "page" in change:
        case = AgentEvalCase(
            case_id="page", expected_tools=("extract_entities",),
            expected_document_id="doc-a", expected_page=2,
            require_sources=True,
        )
    payload = result(**change)
    score = evaluate_agent([case], [payload])
    assert score["task_success_rate"] == 0.0
    assert score["tool_success_rate"] == 1.0


def test_wrong_entity_value_is_task_failure():
    payload = result()
    payload["entities"][0]["value"] = "错误公司"
    assert evaluate_agent([extraction_case()], [payload])["task_success_rate"] == 0.0


def test_transport_error_and_fallback_are_runtime_failures():
    fail = result(status="tool_unavailable", answer="工具暂不可用", event_status="fallback")
    fail["sources"] = []
    fail["entities"] = []
    metrics = evaluate_agent([extraction_case(), AgentEvalCase(
        case_id="second", expected_tools=("extract_entities",),
    )], [None, fail])
    assert metrics["task_success_rate"] == 0.0
    assert metrics["failure_rate"] == 1.0
    assert metrics["tool_success_rate"] == 0.0
    assert metrics["average_agent_steps"] == 1


def test_missing_tool_events_must_not_be_treated_as_tool_success():
    payload = result()
    payload["tool_events"] = []
    scores = evaluate_agent([extraction_case()], [payload])
    assert scores["tool_success_rate"] == 0.0


def test_no_observed_calls_is_not_100_percent_success():
    case = AgentEvalCase(case_id="metadata", expected_tools=("query_document_metadata",))
    score = evaluate_agent([case], [None])
    assert score["tool_success_rate"] is None
    assert score["average_agent_steps"] is None
    assert score["tool_selection_accuracy"] == 0.0


def test_duplicate_case_ids_and_empty_gold_rejected():
    with pytest.raises(ValueError):
        evaluate_agent([extraction_case(), extraction_case()], [None, None])
    with pytest.raises(ValueError):
        evaluate_agent([], [])
    with pytest.raises(ValueError):
        evaluate_agent([AgentEvalCase("x", ())], [None])
