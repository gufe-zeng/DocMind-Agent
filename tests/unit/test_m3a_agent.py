"""M3a LangGraph state transitions and structured tool invocation tests."""

import pytest
from pydantic import ValidationError

from app.agent.graph import build_agent_graph
from app.agent.router import select_tool_plan
from app.tools.registry import (
    DocumentMetadataArgs,
    SearchDocumentsArgs,
    available_tools,
    invoke_tool,
)


def test_router_single_and_compound_intents():
    assert select_tool_plan("合同付款期限是多少？") == ["search_documents"]
    assert select_tool_plan("列出已上传的文档") == ["query_document_metadata"]
    assert select_tool_plan("列出文档，并告诉我付款期限") == [
        "query_document_metadata",
        "search_documents",
    ]


def test_registry_has_only_approved_m3a_tools():
    assert set(available_tools()) == {
        "search_documents",
        "query_document_metadata",
    }
    with pytest.raises(ValidationError):
        SearchDocumentsArgs(query="  ")
    with pytest.raises(ValidationError):
        DocumentMetadataArgs(limit=100)


@pytest.mark.asyncio
async def test_unknown_tool_is_blocked():
    with pytest.raises(ValueError, match="not registered"):
        await invoke_tool("delete_all_documents", arguments={})


@pytest.mark.asyncio
async def test_graph_metadata_then_qa_calls_real_registry_names(monkeypatch):
    calls = []

    async def stub_tool(name, *, arguments):
        calls.append((name, arguments))
        if name == "query_document_metadata":
            return {
                "tool": name,
                "status": "answered",
                "documents": [
                    {
                        "filename": "sample.txt",
                        "status": "indexed",
                        "chunk_count": 1,
                    }
                ],
                "sources": [],
            }
        return {
            "tool": name,
            "status": "answered",
            "answer": "付款期限为三十日。[S1]",
            "sources": [
                {
                    "id": "S1",
                    "document_id": "doc-a",
                    "chunk_id": "chunk-a",
                    "filename": "sample.txt",
                    "page": None,
                }
            ],
        }

    monkeypatch.setattr("app.agent.nodes.invoke_tool", stub_tool)
    graph = build_agent_graph()
    state = await graph.ainvoke(
        {
            "query": "列出文档，并告诉我付款期限",
            "document_id": None,
        }
    )

    assert [name for name, _ in calls] == [
        "query_document_metadata",
        "search_documents",
    ]
    assert state["tools_called"] == [name for name, _ in calls]
    assert state["current_step"] == 2
    assert state["status"] == "answered"
    assert "sample.txt" in state["final_answer"]
    assert "三十日。[S1]" in state["final_answer"]
    assert state["sources"][0]["chunk_id"] == "chunk-a"


@pytest.mark.asyncio
async def test_graph_single_search_tool(monkeypatch):
    async def stub(name, *, arguments):
        assert name == "search_documents"
        assert arguments == {"query": "付款期限是多少？", "document_id": "document-xyz"}
        return {
            "tool": name,
            "status": "answered",
            "answer": "三十日。[S1]",
            "sources": [{"id": "S1"}],
        }

    monkeypatch.setattr("app.agent.nodes.invoke_tool", stub)
    graph = build_agent_graph()
    result = await graph.ainvoke(
        {"query": "付款期限是多少？", "document_id": "document-xyz"}
    )
    assert result["current_step"] == 1
    assert result["tools_called"] == ["search_documents"]
    assert result["final_answer"] == "三十日。[S1]"
