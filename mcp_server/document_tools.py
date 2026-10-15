"""M5a Document MCP read-only tool implementations.

This module contains business logic only. mcp_server.server exposes these
functions through the official MCP SDK over a real stdio transport.

Not a general-purpose filesystem/SQL agent: document IDs are validated,
reads are bounded, and only existing indexed document data is accessible.
"""

from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.rag.retriever import hybrid_search
from app.storage.postgres import get_document
from app.tools.document import load_document_chunks


MAX_DOCUMENT_CHUNKS = 200
MAX_RETURN_CHUNKS = 20
MAX_MCP_TEXT_CHARS = 500


def _id(value: str) -> str:
    """Reject non-UUID identifiers; do not allow paths or free-form filters."""
    return str(UUID(value))


def _chunk_source(chunk: dict, *, text_chars: int = MAX_MCP_TEXT_CHARS) -> dict:
    return {
        "document_id": str(chunk["document_id"]),
        "chunk_id": str(chunk["chunk_id"]),
        "filename": str(chunk["filename"]),
        "page": chunk.get("page"),
        "section": chunk.get("section"),
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "text": str(chunk["text"])[:text_chars],
    }


async def get_document_info(document_id: str) -> dict[str, Any]:
    """Metadata for a single indexed/uploaded document (no bulk text leak)."""
    document_id = _id(document_id)
    data = await get_document(get_settings().postgres_dsn, UUID(document_id))
    if data is None:
        return {"status": "not_found", "document_id": document_id}
    return {
        "status": "found",
        "document_id": document_id,
        "filename": str(data["filename"]),
        "extension": str(data["extension"]),
        "size_bytes": int(data["size_bytes"]),
        "index_status": str(data["status"]),
        "chunk_count": int(data.get("chunk_count") or 0),
        "embedding_model": data.get("embedding_model"),
    }


async def get_document_page_text(document_id: str, page: int) -> dict[str, Any]:
    """Retrieve source-anchored indexed chunks for a PDF's actual page."""
    document_id = _id(document_id)
    if page < 1:
        raise ValueError("page must be a positive 1-based PDF page number.")
    info = await get_document_info(document_id)
    if info["status"] != "found":
        return {"status": "not_found", "document_id": document_id, "page": page, "chunks": []}
    if info["index_status"] != "indexed":
        return {
            "status": "not_indexed", "document_id": document_id,
            "page": page, "chunks": [],
        }
    if info["extension"] != ".pdf":
        return {
            "status": "page_not_applicable", "document_id": document_id,
            "page": page, "chunks": [],
        }
    chunks = await load_document_chunks(document_id, max_chunks=MAX_DOCUMENT_CHUNKS)
    page_chunks = [c for c in chunks if c.get("page") == page]
    if len(page_chunks) > MAX_RETURN_CHUNKS:
        raise RuntimeError("PDF page exceeds the bounded MCP response limit.")
    return {
        "status": "found" if page_chunks else "no_evidence",
        "document_id": document_id, "page": page,
        "chunk_count": len(page_chunks),
        "chunks": [_chunk_source(chunk) for chunk in page_chunks],
    }


async def find_document_clause(
    document_id: str, keyword: str, *, limit: int = 5
) -> dict[str, Any]:
    """Find exact lexical matches in indexed chunks, with source metadata."""
    document_id = _id(document_id)
    keyword = keyword.strip()
    if not 1 <= len(keyword) <= 80:
        raise ValueError("keyword must be 1–80 characters.")
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10.")
    info = await get_document_info(document_id)
    if info["status"] != "found":
        return {
            "status": "not_found", "document_id": document_id,
            "keyword": keyword, "matches": [],
        }
    if info["index_status"] != "indexed":
        return {
            "status": "not_indexed", "document_id": document_id,
            "keyword": keyword, "matches": [],
        }

    chunks = await load_document_chunks(document_id, max_chunks=MAX_DOCUMENT_CHUNKS)
    matched = [c for c in chunks if keyword.lower() in str(c["text"]).lower()]
    return {
        "status": "found" if matched else "no_evidence",
        "document_id": document_id,
        "keyword": keyword,
        "total_matched_chunks": len(matched),
        "returned_matches": min(len(matched), limit),
        "matches": [_chunk_source(c) for c in matched[:limit]],
    }


async def search_indexed_documents(
    query: str,
    *,
    document_id: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Return M2 Dense+BM25+RRF *evidence*, not an unverified LLM answer."""
    query = query.strip()
    if not 1 <= len(query) <= 2000:
        raise ValueError("query must be 1–2000 characters.")
    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10.")
    if document_id is not None:
        document_id = _id(document_id)
    hits = await hybrid_search(
        query, document_id=document_id,
        top_k=limit, candidate_k=20,
    )
    return {
        "status": "found" if hits else "no_evidence",
        "query": query,
        "document_id": document_id,
        "count": len(hits),
        "retrieval": "BGE dense + Chinese bigram BM25 + RRF",
        "chunks": [
            {
                "document_id": h.document_id,
                "chunk_id": h.chunk_id,
                "filename": h.filename,
                "page": h.page,
                "section": h.section,
                "text": h.text[:MAX_MCP_TEXT_CHARS],
                "rrf_score": h.rrf_score,
                "dense_rank": h.dense_rank,
                "sparse_rank": h.sparse_rank,
            }
            for h in hits
        ],
    }
