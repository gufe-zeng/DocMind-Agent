"""M2b RAG pipeline behavior, with mocked model dependencies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.client import LLMResult
from app.rag import pipeline
from app.rag.reranker import RerankedHit
from app.rag.retriever import RetrievalHit


def hit() -> RetrievalHit:
    return RetrievalHit(
        document_id="doc1",
        chunk_id="chunk1",
        filename="sample_contract.pdf",
        page=2,
        section=None,
        text="付款期限为三十日。",
        rrf_score=0.0327,
        dense_rank=1,
        sparse_rank=1,
    )


def settings() -> SimpleNamespace:
    return SimpleNamespace(
        rag_candidate_k=8,
        rag_evidence_k=2,
        rag_max_evidence_chars=160,
        rag_max_answer_tokens=128,
        reranker_model="BAAI/bge-reranker-base",
        embedding_cache_dir="/tmp/cache",
        llm_base_url="http://127.0.0.1:8000/v1",
        llm_api_key="EMPTY",
        llm_model="Qwen/Qwen3-0.6B",
    )


@pytest.mark.asyncio
async def test_rag_pipeline_with_valid_citation(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "get_settings", settings)
    monkeypatch.setattr(pipeline, "hybrid_search", AsyncMock(return_value=[hit()]))
    monkeypatch.setattr(
        pipeline, "rerank_hits",
        lambda query, hits, **kwargs: [RerankedHit(hits[0], 3.2)],
    )
    monkeypatch.setattr(
        pipeline,
        "complete_chat",
        AsyncMock(return_value=LLMResult("付款期限为三十日。[S1]", 100, 20)),
    )
    answer = await pipeline.answer_document_question("  付款期限  ", document_id="doc1")
    assert answer.status == "answered"
    assert answer.citation_valid
    assert answer.citations_used == ("S1",)
    assert answer.sources[0].page == 2
    assert answer.prompt_tokens == 100


@pytest.mark.asyncio
async def test_invalid_citation_never_returns_hallucinated_answer(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "get_settings", settings)
    monkeypatch.setattr(pipeline, "hybrid_search", AsyncMock(return_value=[hit()]))
    monkeypatch.setattr(
        pipeline, "rerank_hits",
        lambda query, hits, **kwargs: [RerankedHit(hits[0], 3.2)],
    )
    monkeypatch.setattr(
        pipeline,
        "complete_chat",
        AsyncMock(return_value=LLMResult("随便编造。[S99]", None, None)),
    )
    answer = await pipeline.answer_document_question("付款期限")
    assert answer.status == "citation_unverified"
    assert not answer.citation_valid
    assert "随便编造" not in answer.answer


@pytest.mark.asyncio
async def test_no_evidence_never_calls_llm(monkeypatch) -> None:
    monkeypatch.setattr(pipeline, "get_settings", settings)
    monkeypatch.setattr(pipeline, "hybrid_search", AsyncMock(return_value=[]))
    llm = AsyncMock()
    monkeypatch.setattr(pipeline, "complete_chat", llm)
    answer = await pipeline.answer_document_question("付款期限", document_id="doc1")
    assert answer.status == "no_evidence"
    assert answer.sources == []
    llm.assert_not_called()
