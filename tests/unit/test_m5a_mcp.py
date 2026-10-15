"""M5a offline checks for bounded document MCP read-only handlers."""

from uuid import uuid4

import pytest

from mcp_server import document_tools


@pytest.mark.asyncio
async def test_document_metadata_comes_from_postgres(monkeypatch):
    from uuid import UUID
    doc = str(uuid4())

    async def fake_get_document(dsn, document_id):
        assert document_id == UUID(doc)
        return {
            "id": document_id,
            "filename": "contract.pdf",
            "extension": ".pdf",
            "size_bytes": 100,
            "status": "indexed",
            "chunk_count": 2,
            "embedding_model": "BAAI/bge-small-zh-v1.5",
        }

    monkeypatch.setattr(
        document_tools,
        "get_settings",
        lambda: type("Settings", (), {"postgres_dsn": "postgres://demo"})(),
    )
    monkeypatch.setattr(document_tools, "get_document", fake_get_document)
    result = await document_tools.get_document_info(doc)
    assert result["document_id"] == doc
    assert result["filename"] == "contract.pdf"
    assert result["chunk_count"] == 2


@pytest.mark.asyncio
async def test_find_clause_enforces_source_and_bounds(monkeypatch):
    doc = str(uuid4())

    async def get_info(document_id):
        return {"status": "found", "index_status": "indexed"}

    async def scan(document_id, **kwargs):
        return [
            {
                "document_id": doc,
                "chunk_id": "1",
                "filename": "a.txt",
                "chunk_index": 0,
                "page": None,
                "section": None,
                "text": "违约责任：甲方应当支付违约金。",
            },
            {
                "document_id": doc,
                "chunk_id": "2",
                "filename": "a.txt",
                "chunk_index": 1,
                "page": None,
                "section": None,
                "text": "履行期限为三十日。",
            },
        ]

    monkeypatch.setattr(document_tools, "get_document_info", get_info)
    monkeypatch.setattr(document_tools, "load_document_chunks", scan)
    result = await document_tools.find_document_clause(doc, "违约责任", limit=5)
    assert result["total_matched_chunks"] == 1
    assert result["matches"][0]["chunk_id"] == "1"
    assert result["matches"][0]["document_id"] == doc

    with pytest.raises(ValueError):
        await document_tools.find_document_clause(doc, " ", limit=5)
    with pytest.raises(ValueError):
        await document_tools.find_document_clause(doc, "责任", limit=11)
    with pytest.raises(ValueError):
        await document_tools.get_document_page_text(doc, 0)


@pytest.mark.asyncio
async def test_mcp_search_delegates_to_accepted_hybrid_retrieval(monkeypatch):
    doc = str(uuid4())
    seen = {}

    async def fake_search(query, **kwargs):
        seen.update(kwargs)
        return [
            type("Hit", (), {
                "document_id": doc,
                "chunk_id": "chunk-id",
                "filename": "doc.txt",
                "page": None,
                "section": None,
                "text": "合同违约责任",
                "rrf_score": 0.032,
                "dense_rank": 1,
                "sparse_rank": 1,
            })()
        ]

    monkeypatch.setattr(document_tools, "hybrid_search", fake_search)
    response = await document_tools.search_indexed_documents(
        "违约责任", document_id=doc, limit=2
    )
    assert seen["document_id"] == doc
    assert seen["top_k"] == 2
    assert response["chunks"][0]["chunk_id"] == "chunk-id"
    assert response["chunks"][0]["dense_rank"] == 1
    with pytest.raises(ValueError):
        await document_tools.search_indexed_documents("", document_id=doc)
    with pytest.raises(ValueError):
        await document_tools.get_document_info("../etc/passwd")
