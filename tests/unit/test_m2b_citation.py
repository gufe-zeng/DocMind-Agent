"""M2b citation metadata integrity and reference ID tests."""

from app.rag.citation import build_sources, format_evidence, validate_answer_citations
from app.rag.reranker import RerankedHit
from app.rag.retriever import RetrievalHit


def sample_source() -> list:
    hit = RetrievalHit(
        document_id="document-a",
        chunk_id="chunk-01",
        filename="contract.pdf",
        page=3,
        section=None,
        text="合同付款期限为三十日。",
        rrf_score=0.031,
        dense_rank=1,
        sparse_rank=1,
    )
    return build_sources([RerankedHit(hit=hit, reranker_score=2.5)])


def test_build_sources_has_real_page_and_chunk() -> None:
    sources = sample_source()
    assert sources[0].id == "S1"
    assert sources[0].page == 3
    assert sources[0].chunk_id == "chunk-01"
    assert "[S1]" in format_evidence(sources)
    assert "第3页" in format_evidence(sources)


def test_valid_citation_ids_are_accepted() -> None:
    outcome = validate_answer_citations("付款期限为三十日。[S1]", sample_source())
    assert outcome.valid
    assert outcome.used_ids == ("S1",)


def test_fabricated_citation_is_rejected() -> None:
    outcome = validate_answer_citations("付款期限为三十日。[S5]", sample_source())
    assert not outcome.valid
    assert outcome.invalid_ids == ("S5",)


def test_missing_citation_is_rejected_for_factual_answer() -> None:
    assert not validate_answer_citations("付款期限为三十日。", sample_source()).valid


def test_empty_evidence_refusal_can_omit_citations() -> None:
    assert validate_answer_citations(
        "证据不足，无法确定。", [], require_at_least_one=False
    ).valid
