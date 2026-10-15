"""M5b real Agent-to-MCP end-to-end test (all four MCP tools).

The test exercises POST /v1/chat and watches the Agent's tools_called and
mcp_tools_called fields, real source IDs and verified document scope.
This does not call vLLM and does not bypass the MCP stdio transport.
"""

import asyncio

import fitz
import httpx


def make_pdf() -> bytes:
    pdf = fitz.open()
    first = pdf.new_page()
    first.insert_text((72, 72), "DOCMIND AGREEMENT PAGE ONE")
    second = pdf.new_page()
    second.insert_text((72, 72), "MCP SECOND PAGE DELIVERY EVIDENCE")
    data = pdf.tobytes()
    pdf.close()
    return data


async def index(http: httpx.AsyncClient, name: str, content: bytes, content_type: str) -> str:
    upload = await http.post(
        "/v1/documents", files={"file": (name, content, content_type)}
    )
    upload.raise_for_status()
    doc_id = upload.json()["document_id"]
    indexed = await http.post(f"/v1/documents/{doc_id}/index")
    indexed.raise_for_status()
    assert indexed.json()["status"] == "indexed"
    return doc_id


async def agent_call(
    http: httpx.AsyncClient,
    query: str, document_id: str,
    *,
    expected_agent_tools: list[str],
    expected_mcp_tools: list[str],
) -> dict:
    response = await http.post(
        "/v1/chat",
        json={"query": query, "document_id": document_id},
    )
    if response.status_code != 200:
        print(
            "Agent error:", response.status_code, response.text[:700], flush=True
        )
    response.raise_for_status()
    payload = response.json()
    print(
        f"QUERY={query}\n"
        f"status={payload['status']} "
        f"tools={payload['tools_called']} "
        f"mcp_tools={payload['mcp_tools_called']}\n"
        f"answer={payload['answer'][:600]}",
        flush=True,
    )
    assert payload["tools_called"] == expected_agent_tools, payload
    assert payload["mcp_tools_called"] == expected_mcp_tools, payload
    assert payload["steps"] == len(expected_agent_tools), payload
    assert payload["plan_source"] == "rules", payload
    return payload


def verify_cited_chunks(payload: dict, document_id: str, page=None) -> None:
    assert payload["status"] == "answered", payload
    sources = payload["sources"]
    assert sources, payload
    assert len({source["id"] for source in sources}) == len(sources), payload
    for source in sources:
        assert source["document_id"] == document_id, payload
        assert source["chunk_id"], payload
        assert f"[{source['id']}]" in payload["answer"], payload
        if page is not None:
            assert source["page"] == page, payload


async def main() -> None:
    contract = (
        "合同付款期限：甲方在乙方验收合格后三十日内支付合同款项。\n"
        "违约责任：若甲方逾期付款，应按约定每日支付违约金。"
    )
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False
    ) as http:
        txt_id = await index(
            http, "m5b_contract.txt", contract.encode("utf-8"), "text/plain"
        )
        pdf_id = await index(
            http, "m5b_pages.pdf", make_pdf(), "application/pdf"
        )
        print("Indexed contract/pdf:", txt_id, pdf_id, flush=True)

        clause = await agent_call(
            http, "通过MCP查找违约责任条款", txt_id,
            expected_agent_tools=["mcp_find_clause"],
            expected_mcp_tools=["find_clause"],
        )
        verify_cited_chunks(clause, txt_id)
        assert "违约责任" in clause["answer"]
        print("PASS Agent -> MCP find_clause source citation", flush=True)

        metadata = await agent_call(
            http, "通过MCP查询文档信息", txt_id,
            expected_agent_tools=["mcp_get_document"],
            expected_mcp_tools=["get_document"],
        )
        assert metadata["status"] == "answered"
        assert "m5b_contract.txt" in metadata["answer"]
        assert metadata["sources"] == []
        print("PASS Agent -> MCP get_document metadata", flush=True)

        page = await agent_call(
            http, "通过MCP读取第2页的内容", pdf_id,
            expected_agent_tools=["mcp_get_document_page"],
            expected_mcp_tools=["get_document_page"],
        )
        verify_cited_chunks(page, pdf_id, page=2)
        assert "MCP SECOND PAGE" in page["answer"]
        print("PASS Agent -> MCP get_document_page PDF provenance", flush=True)

        search = await agent_call(
            http, "通过MCP检索逾期付款违约金", txt_id,
            expected_agent_tools=["mcp_search_documents"],
            expected_mcp_tools=["search_documents"],
        )
        verify_cited_chunks(search, txt_id)
        print("PASS Agent -> MCP search_documents Hybrid RAG evidence", flush=True)

        combined = await agent_call(
            http, "通过MCP查询文档信息并查找违约责任条款", txt_id,
            expected_agent_tools=["mcp_get_document", "mcp_find_clause"],
            expected_mcp_tools=["get_document", "find_clause"],
        )
        verify_cited_chunks(combined, txt_id)
        assert "m5b_contract.txt" in combined["answer"]
        print("PASS LangGraph multi-tool MCP sequence and citations", flush=True)

    print("M5b AGENT MCP PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
