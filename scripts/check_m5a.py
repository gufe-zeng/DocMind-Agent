"""M5a: verify a real MCP stdio subprocess and four document tools.

The test uses genuine Postgres/Qdrant and the existing BGE cache. Tool
discovery and calls cross the actual MCP ClientSession/JSON-RPC boundary.
The Agent is not routed through MCP until M5b.
"""

import asyncio
import json
import os
import sys

import fitz
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPECTED = {
    "search_documents",
    "get_document",
    "get_document_page",
    "find_clause",
}


async def _index(client: httpx.AsyncClient, name: str, contents: bytes, mime: str) -> str:
    response = await client.post(
        "/v1/documents", files={"file": (name, contents, mime)}
    )
    response.raise_for_status()
    doc_id = response.json()["document_id"]
    index = await client.post(f"/v1/documents/{doc_id}/index")
    index.raise_for_status()
    assert index.json()["status"] == "indexed"
    return doc_id


def _pdf() -> bytes:
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text(
        (72, 72),
        "DOCMIND PAGE ONE CONTRACT SOURCE",
    )
    p2 = doc.new_page()
    p2.insert_text(
        (72, 72),
        "DOCMIND PAGE TWO DELIVERY TERM",
    )
    data = doc.tobytes()
    doc.close()
    return data


def _payload(result, tool: str) -> dict:
    assert not result.isError, f"{tool} failed: {result.content}"
    payload = getattr(result, "structuredContent", None)
    if payload is None:
        assert result.content, f"No tool content: {tool}"
        payload = json.loads(result.content[0].text)
    if isinstance(payload, dict) and set(payload.keys()) == {"result"}:
        payload = payload["result"]
    assert isinstance(payload, dict), (tool, payload)
    return payload


async def main() -> None:
    contract = (
        "甲方应在验收后三十日内支付合同款项。\n"
        "违约责任：若付款逾期，应按合同约定支付违约金。"
    )
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600,
        trust_env=False,
    ) as http:
        txt = await _index(
            http, "m5a_contract.txt", contract.encode(), "text/plain"
        )
        pdf = await _index(
            http, "m5a_pages.pdf", _pdf(), "application/pdf"
        )
        print("Indexed documents:", txt, pdf, flush=True)

    env = dict(os.environ)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        env=env,
    )

    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == EXPECTED, names
            print("PASS MCP initialize + discover four official tools", flush=True)

            document = _payload(
                await session.call_tool(
                    "get_document", arguments={"document_id": txt}
                ), "get_document",
            )
            assert document["status"] == "found", document
            assert document["document_id"] == txt
            assert document["filename"] == "m5a_contract.txt"
            assert document["index_status"] == "indexed"
            print("PASS get_document metadata through MCP", flush=True)

            page = _payload(
                await session.call_tool(
                    "get_document_page",
                    arguments={"document_id": pdf, "page": 2},
                ), "get_document_page",
            )
            assert page["status"] == "found", page
            assert page["page"] == 2, page
            assert page["chunks"], page
            assert all(item["page"] == 2 for item in page["chunks"]), page
            print("PASS get_document_page with real PDF page provenance", flush=True)

            clause = _payload(
                await session.call_tool(
                    "find_clause",
                    arguments={
                        "document_id": txt,
                        "keyword": "违约责任",
                        "limit": 5,
                    },
                ), "find_clause",
            )
            assert clause["status"] == "found", clause
            assert clause["matches"][0]["document_id"] == txt
            assert clause["matches"][0]["chunk_id"]
            print("PASS find_clause source-anchored lexical result", flush=True)

            found = _payload(
                await session.call_tool(
                    "search_documents",
                    arguments={
                        "query": "逾期违约金责任",
                        "document_id": txt,
                        "limit": 3,
                    },
                ), "search_documents",
            )
            assert found["status"] == "found", found
            assert found["chunks"], found
            assert all(item["document_id"] == txt for item in found["chunks"])
            assert found["chunks"][0]["chunk_id"]
            print("PASS MCP search_documents Dense/BM25/RRF evidence", flush=True)

    print("M5a MCP PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
