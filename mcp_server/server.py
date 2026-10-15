"""Real MCP Document Server, using Model Context Protocol over stdio.

Run from the project root (inside the API Docker image):
    python -m mcp_server.server

Stdout is reserved for JSON-RPC. Never print to stdout in server code.
All four MCP tools are read-only. No arbitrary shell/SQL/file operations.
"""

from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server.document_tools import (
    find_document_clause,
    get_document_info,
    get_document_page_text,
    search_indexed_documents,
)


mcp = FastMCP("DocMind Document Server")


@mcp.tool()
async def search_documents(
    query: str,
    document_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search indexed document chunks with Dense+BM25+RRF and source metadata."""
    return await search_indexed_documents(query, document_id=document_id, limit=limit)


@mcp.tool()
async def get_document(document_id: str) -> dict[str, Any]:
    """Read a document's PostgreSQL metadata by its UUID."""
    return await get_document_info(document_id)


@mcp.tool()
async def get_document_page(document_id: str, page: int) -> dict[str, Any]:
    """Read indexed source chunks for a specific 1-based PDF page."""
    return await get_document_page_text(document_id, page)


@mcp.tool()
async def find_clause(
    document_id: str, keyword: str, limit: int = 5
) -> dict[str, Any]:
    """Locate an exact clause phrase in an indexed document with citations."""
    return await find_document_clause(document_id, keyword, limit=limit)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
