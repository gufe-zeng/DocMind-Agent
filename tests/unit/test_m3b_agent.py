"""M3b offline checks for source-grounded extraction and tool planning."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agent import router
from app.agent.graph import build_agent_graph
from app.agent.router import PlanDecision
from app.llm.client import LLMResult
from app.tools.extraction import extract_entities
from app.tools.registry import ExtractEntitiesArgs, SummarizeDocumentArgs


DOCUMENT_ID = str(uuid4())


def sample_chunk():
    return {
        "document_id": DOCUMENT_ID,
        "chunk_id": str(uuid4()),
        "filename": "contract.txt",
        "chunk_index": 0,
        "page": None,
        "section": None,
        "text": (
            "甲方：甲方示例科技有限公司。\n"
            "乙方：乙方示例服务有限公司。\n"
            "付款条款：乙方服务经验收后，甲方应在三十日内支付款项。"
        ),
    }


def test_new_router_intents_preserve_old_qa():
    assert router.select_tool_plan("合同付款期限是多少？") == ["search_documents"]
    assert router.select_tool_plan("列出已上传的文档") == ["query_document_metadata"]
    assert router.select_tool_plan("提取合同甲乙方和付款期限") == ["extract_entities"]
    assert router.select_tool_plan("总结合同内容") == ["summarize_document"]
    assert router.select_tool_plan("提取甲乙方并总结合同") == [
        "extract_entities", "summarize_document"
    ]


@pytest.mark.asyncio
async def test_extraction_reads_real_source_text_without_llm(monkeypatch):
    async def stub_chunks(document_id, **kwargs):
        assert document_id == DOCUMENT_ID
        return [sample_chunk()]

    monkeypatch.setattr("app.tools.extraction.load_document_chunks", stub_chunks)
    result = await extract_entities(
        ExtractEntitiesArgs(query="提取甲乙方和付款期限", document_id=DOCUMENT_ID)
    )
    assert result["status"] == "answered"
    fields = {entity["field"]: entity["value"] for entity in result["entities"]}
    assert fields["甲方"] == "甲方示例科技有限公司"
    assert fields["乙方"] == "乙方示例服务有限公司"
    assert fields["付款期限"] == "三十日"
    assert len({row["id"] for row in result["sources"]}) == len(result["sources"])
    assert all(row["chunk_id"] == result["sources"][0]["chunk_id"] for row in result["entities"])
    assert all(entity["source_id"] in {source["id"] for source in result["sources"]}
               for entity in result["entities"])


@pytest.mark.asyncio
async def test_llm_planner_validated_and_fallback(monkeypatch):
    mock_settings = SimpleNamespace(
        llm_base_url="http://invalid/v1",
        llm_api_key="EMPTY",
        llm_model="Qwen/Qwen3-0.6B",
    )
    monkeypatch.setattr(router, "get_settings", lambda: mock_settings)

    async def valid_model(messages, **kwargs):
        return LLMResult(
            '{"tools":["summarize_document","extract_entities"]}', 18, 23
        )

    monkeypatch.setattr(router, "complete_chat", valid_model)
    result = await router.plan_tools(
        "请提取甲乙方，并总结这份合同", document_id=DOCUMENT_ID
    )
    assert result.source == "llm_validated"
    assert result.tools == ["summarize_document", "extract_entities"]

    async def forbidden_model(messages, **kwargs):
        return LLMResult(
            '{"tools":["delete_documents","extract_entities"]}', 18, 23
        )

    monkeypatch.setattr(router, "complete_chat", forbidden_model)
    fallback = await router.plan_tools(
        "请提取甲乙方，并总结这份合同", document_id=DOCUMENT_ID
    )
    assert fallback.source == "rule_fallback"
    assert fallback.tools == ["extract_entities", "summarize_document"]
    assert fallback.reason == "ValueError"


@pytest.mark.asyncio
async def test_metadata_does_not_need_the_planning_model(monkeypatch):
    async def unavailable_model(*args, **kwargs):
        raise AssertionError("Simple tasks should not call the planning model")

    monkeypatch.setattr(router, "complete_chat", unavailable_model)
    result = await router.plan_tools("列出已上传文档")
    assert result.source == "rules"


@pytest.mark.asyncio
async def test_graph_rekeys_independent_source_ids(monkeypatch):
    async def fixed_plan(query, document_id=None):
        return PlanDecision(
            tools=["extract_entities", "summarize_document"],
            source="llm_validated",
        )

    async def stub_tool(name, *, arguments):
        if name == "extract_entities":
            return {
                "tool": name,
                "status": "answered",
                "answer": "甲方：示例公司 [S1]",
                "entities": [
                    {
                        "field": "甲方",
                        "value": "示例公司",
                        "source_id": "S1",
                        "chunk_id": "chunk-a",
                    }
                ],
                "sources": [
                    {"id": "S1", "chunk_id": "chunk-a", "document_id": DOCUMENT_ID}
                ],
            }
        return {
            "tool": name,
            "status": "answered",
            "answer": "付款条件：验收后三十日。[S1]",
            "sources": [
                {"id": "S1", "chunk_id": "chunk-b", "document_id": DOCUMENT_ID}
            ],
        }

    monkeypatch.setattr("app.agent.nodes.plan_tools", fixed_plan)
    monkeypatch.setattr("app.agent.nodes.invoke_tool", stub_tool)
    state = await build_agent_graph().ainvoke(
        {"query": "提取并总结合同", "document_id": DOCUMENT_ID}
    )
    assert state["tools_called"] == ["extract_entities", "summarize_document"]
    assert state["plan_source"] == "llm_validated"
    assert state["status"] == "answered"
    assert len(state["sources"]) == 2
    assert [source["id"] for source in state["sources"]] == ["S1", "S2"]
    assert [source["chunk_id"] for source in state["sources"]] == [
        "chunk-a", "chunk-b"
    ]
    assert "示例公司 [S1]" in state["final_answer"]
    assert "三十日。[S2]" in state["final_answer"]
    assert state["entities"][0]["source_id"] == "S1"


def test_summary_requires_document_uuid():
    with pytest.raises(Exception):
        SummarizeDocumentArgs(query="总结文档", document_id=None)
