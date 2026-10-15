"""M5b offline checks: real Agent flow uses validated MCP bridge.

Transport behavior is checked separately from Agent state to prevent
accidental use of local Python document functions in place of MCP.
"""

from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agent.graph import build_agent_graph
from app.agent.router import select_tool_plan
from app.mcp_client import adapter
from app.tools.registry import available_tools, invoke_tool


def test_explicit_mcp_intents_do_not_break_existing_routes():
    assert select_tool_plan("根据合同付款期限是多少天？") == ["search_documents"]
    assert select_tool_plan("通过MCP查找违约责任条款") == ["mcp_find_clause"]
    assert select_tool_plan("通过MCP查询文档信息") == ["mcp_get_document"]
    assert select_tool_plan("通过MCP读取第2页") == ["mcp_get_document_page"]
    assert select_tool_plan("通过MCP检索逾期付款违约金") == ["mcp_search_documents"]
    assert select_tool_plan("通过MCP查询文档信息并查找违约责任条款") == [
        "mcp_get_document", "mcp_find_clause",
    ]


@pytest.mark.asyncio
async def test_mcp_registry_rejects_unregistered_and_invalid_parameters():
    assert {
        "mcp_find_clause", "mcp_get_document", "mcp_get_document_page",
        "mcp_search_documents",
    }.issubset(available_tools())

    with pytest.raises(ValueError):
        await invoke_tool("mcp_delete_document", arguments={"document_id": "abc"})
    with pytest.raises(ValidationError):
        await invoke_tool(
            "mcp_get_document", arguments={"document_id": "../../secret"}
        )
    with pytest.raises(ValidationError):
        await invoke_tool(
            "mcp_get_document_page",
            arguments={"document_id": str(uuid4()), "page": 0},
        )


def test_mcp_response_unwraps_fastmcp_structured_content():
    result = SimpleNamespace(
        isError=False,
        structuredContent={"result": {"status": "found", "chunk_count": 1}},
        content=[],
    )
    assert adapter._extract_response(result, "get_document") == {
        "status": "found", "chunk_count": 1
    }

    fallback = SimpleNamespace(
        isError=False,
        structuredContent=None,
        content=[SimpleNamespace(text=json.dumps({"status": "found"}))],
    )
    assert adapter._extract_response(fallback, "get_document") == {
        "status": "found"
    }

    error = SimpleNamespace(isError=True, content=[], structuredContent=None)
    with pytest.raises(adapter.DocumentMCPError):
        adapter._extract_response(error, "get_document")


@pytest.mark.asyncio
async def test_adapter_speaks_initialize_list_and_call(monkeypatch):
    events = []

    @asynccontextmanager
    async def fake_stdio(params):
        assert params.args == ["-m", "mcp_server.server"]
        events.append("spawn_stdio")
        yield (object(), object())

    class FakeClientSession:
        def __init__(self, reader, writer, **kwargs):
            assert "read_timeout_seconds" in kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def initialize(self):
            events.append("initialize")

        async def list_tools(self):
            events.append("tools/list")
            return SimpleNamespace(
                tools=[SimpleNamespace(name="find_clause")]
            )

        async def call_tool(self, name, arguments):
            events.append(f"tools/call:{name}")
            assert arguments == {"document_id": "demo", "keyword": "责任"}
            return SimpleNamespace(
                isError=False,
                structuredContent={"result": {"status": "found", "keyword": "责任"}},
                content=[],
            )

    monkeypatch.setattr(adapter, "stdio_client", fake_stdio)
    monkeypatch.setattr(adapter, "ClientSession", FakeClientSession)
    found = await adapter.call_document_mcp(
        "find_clause",
        arguments={"document_id": "demo", "keyword": "责任"},
    )
    assert found["status"] == "found"
    assert events == [
        "spawn_stdio", "initialize", "tools/list", "tools/call:find_clause",
    ]
    with pytest.raises(ValueError):
        await adapter.call_document_mcp("delete_all", arguments={})


@pytest.mark.asyncio
async def test_langgraph_uses_real_mcp_adapter_and_cites_source(monkeypatch):
    document_id = str(uuid4())
    calls = []

    async def mock_mcp_call(name, *, arguments, **kwargs):
        calls.append((name, arguments))
        assert name == "find_clause"
        assert arguments["document_id"] == document_id
        assert arguments["keyword"] == "违约责任"
        return {
            "status": "found",
            "document_id": document_id,
            "matches": [
                {
                    "document_id": document_id,
                    "chunk_id": "abc-123",
                    "filename": "contract.txt",
                    "page": None,
                    "section": None,
                    "text": "违约责任：甲方逾期付款承担违约金。",
                }
            ],
        }

    monkeypatch.setattr("app.tools.mcp_bridge.call_document_mcp", mock_mcp_call)
    graph = build_agent_graph()
    result = await graph.ainvoke({
        "query": "通过MCP查找违约责任条款",
        "document_id": document_id,
    })
    assert calls and calls[0][0] == "find_clause"
    assert result["tools_called"] == ["mcp_find_clause"]
    assert result["tool_results"][0]["mcp_tool"] == "find_clause"
    assert result["tool_results"][0]["mcp_transport"] == "stdio"
    assert "[S1]" in result["final_answer"]
    assert result["sources"][0]["chunk_id"] == "abc-123"
    assert result["sources"][0]["document_id"] == document_id


@pytest.mark.asyncio
async def test_mcp_bridge_rejects_scoped_data_mismatch(monkeypatch):
    from app.tools.mcp_bridge import mcp_find_clause
    from app.tools.registry import MCPClauseArgs

    async def mismatch(name, *, arguments, **kwargs):
        return {
            "document_id": str(uuid4()),
            "status": "found",
            "matches": [],
        }
    monkeypatch.setattr("app.tools.mcp_bridge.call_document_mcp", mismatch)
    with pytest.raises(RuntimeError, match="scope mismatch"):
        await mcp_find_clause(
            MCPClauseArgs(document_id=uuid4(), keyword="违约责任")
        )
