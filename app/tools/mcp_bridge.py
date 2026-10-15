"""M5b: adapt the frozen Document MCP tools into LangGraph business results.

The MCP process owns actual source retrieval; this bridge only validates
scope and turns returned evidence into deterministic, cited Agent outputs.
The bridge never fabricates a page number or silently falls back to a local
Python implementation on MCP errors.
"""

import re
from typing import Any

from app.mcp_client.adapter import call_document_mcp
from app.tools.registry import (
    MCPDocumentArgs,
    MCPPageArgs,
    MCPClauseArgs,
    MCPSearchArgs,
)


CLAUSE_TERMS = (
    "违约责任", "违约金", "付款期限", "争议解决",
    "保密条款", "交付期限", "验收标准",
    "付款", "交付", "保密", "验收",
)


def clause_keyword_from_query(query: str) -> str:
    for phrase in CLAUSE_TERMS:
        if phrase in query:
            return phrase
    raise ValueError("MCP clause search needs a supported explicit keyword.")


def page_number_from_query(query: str) -> int:
    match = re.search(r"第\s*(\d{1,4})\s*页", query)
    if match is None:
        raise ValueError("MCP page lookup requires an explicit '第N页'.")
    value = int(match.group(1))
    if value < 1:
        raise ValueError("MCP page numbers start from 1.")
    return value


def _clean_excerpt(text: str) -> str:
    # A snippet is untrusted document content, not a source label.
    # Never allow literal [S99] inside quoted text to masquerade as our ID.
    return re.sub(r"\[S\d+\]", "[文内标记]", text).replace("\x00", "").strip()


def _source(row: dict[str, Any], source_id: str) -> dict[str, Any]:
    """Never invent source provenance missing from the MCP tool result."""
    required = ("document_id", "chunk_id", "filename", "text")
    if not all(row.get(key) for key in required):
        raise RuntimeError("MCP evidence is missing source provenance.")
    return {
        "id": source_id,
        "document_id": str(row["document_id"]),
        "chunk_id": str(row["chunk_id"]),
        "filename": str(row["filename"]),
        "page": row.get("page"),
        "section": row.get("section"),
        "evidence": str(row["text"])[:500],
    }


def _result_with_evidence(
    tool: str, mcp_tool: str, payload: dict, rows: list[dict],
) -> dict[str, Any]:
    if payload.get("status") not in ("found", "no_evidence"):
        if payload.get("status") in ("not_found", "not_indexed", "page_not_applicable"):
            return {
                "tool": tool, "mcp_tool": mcp_tool, "mcp_transport": "stdio",
                "status": "no_evidence", "answer": f"文档不可读取：{payload['status']}",
                "sources": [],
            }
        raise RuntimeError(f"Unexpected MCP status: {payload.get('status')!r}")

    if not rows:
        return {
            "tool": tool, "mcp_tool": mcp_tool, "mcp_transport": "stdio",
            "status": "no_evidence", "answer": "该范围内没有检索到相关文档证据。",
            "sources": [],
        }

    if len(rows) > 20:
        raise RuntimeError("MCP tool returned too many evidence chunks.")
    expected_document = payload.get("document_id")
    if expected_document is not None and any(
        row.get("document_id") != expected_document for row in rows
    ):
        raise RuntimeError("MCP evidence scope differs from the tool result.")
    sources: list[dict] = []
    answer_lines: list[str] = []
    for index, row in enumerate(rows, start=1):
        source_id = f"S{index}"
        source = _source(row, source_id)
        sources.append(source)
        # Include a bounded verbatim excerpt; never claim model inference.
        quote = _clean_excerpt(source["evidence"])
        answer_lines.append(f"来源片段：{quote} [{source_id}]")

    return {
        "tool": tool,
        "mcp_tool": mcp_tool,
        "mcp_transport": "stdio",
        "status": "answered",
        "answer": "\n".join(answer_lines),
        "sources": sources,
    }


async def mcp_find_clause(args: MCPClauseArgs) -> dict[str, Any]:
    payload = await call_document_mcp(
        "find_clause",
        arguments={"document_id": str(args.document_id), "keyword": args.keyword, "limit": args.limit},
    )
    if payload.get("document_id") != str(args.document_id):
        raise RuntimeError("MCP clause result document scope mismatch.")
    return _result_with_evidence(
        "mcp_find_clause", "find_clause", payload, payload.get("matches", []),
    )


async def mcp_get_document(args: MCPDocumentArgs) -> dict[str, Any]:
    payload = await call_document_mcp(
        "get_document", arguments={"document_id": str(args.document_id)}
    )
    if payload.get("document_id") != str(args.document_id):
        raise RuntimeError("MCP document response scope mismatch.")
    status = payload.get("status")
    if status == "not_found":
        answer = "没有找到该文档。"
    elif status == "found":
        answer = (
            f"文档：{payload['filename']}；索引状态：{payload['index_status']}；"
            f"片段数量：{payload['chunk_count']}。"
        )
    else:
        raise RuntimeError("Invalid MCP document metadata status.")
    return {
        "tool": "mcp_get_document",
        "mcp_tool": "get_document",
        "mcp_transport": "stdio",
        "status": "answered" if status == "found" else "no_evidence",
        "answer": answer,
        "sources": [],
    }


async def mcp_get_document_page(args: MCPPageArgs) -> dict[str, Any]:
    payload = await call_document_mcp(
        "get_document_page",
        arguments={"document_id": str(args.document_id), "page": args.page},
    )
    if payload.get("document_id") != str(args.document_id) or payload.get("page") != args.page:
        raise RuntimeError("MCP PDF page response scope mismatch.")
    return _result_with_evidence(
        "mcp_get_document_page", "get_document_page",
        payload, payload.get("chunks", []),
    )


async def mcp_search_documents(args: MCPSearchArgs) -> dict[str, Any]:
    payload = await call_document_mcp(
        "search_documents",
        arguments={
            "query": args.query,
            "document_id": str(args.document_id) if args.document_id else None,
            "limit": args.limit,
        },
    )
    if args.document_id and payload.get("document_id") != str(args.document_id):
        raise RuntimeError("MCP search response document scope mismatch.")
    for row in payload.get("chunks", []):
        if args.document_id and row.get("document_id") != str(args.document_id):
            raise RuntimeError("MCP returned evidence outside requested document.")
    return _result_with_evidence(
        "mcp_search_documents", "search_documents",
        payload, payload.get("chunks", []),
    )
