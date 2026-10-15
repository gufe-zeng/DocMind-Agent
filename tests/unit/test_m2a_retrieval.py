"""M2a offline unit tests for Chinese BM25 and rank fusion."""

import pytest

from app.rag.fusion import reciprocal_rank_fusion
from app.rag.sparse import bm25_rank, lexical_tokens
from app.rag.retriever import _document_filter


def test_chinese_bigrams_and_lowercase_english() -> None:
    tokens = lexical_tokens("合同付款期限 API-2026")
    assert "合同" in tokens and "付款" in tokens and "期限" in tokens
    assert "api" in tokens and "2026" in tokens


def test_bm25_finds_relevant_contract_term() -> None:
    documents = {
        "payment": "甲方应在验收后三十日内支付合同款项，付款期限为三十日。",
        "breach": "乙方逾期履约应承担违约责任。",
        "delivery": "服务交付应在六十日内完成。",
    }
    result = bm25_rank("付款期限", documents, limit=3)
    assert result and result[0][0] == "payment"
    assert all(score > 0 for _, score in result)


def test_bm25_empty_and_no_matching_terms() -> None:
    assert bm25_rank("查询", {}, limit=3) == []
    assert bm25_rank("C++", {"a": "甲方付款"}, limit=3) == []
    with pytest.raises(ValueError):
        bm25_rank("付款", {"a": "付款"}, k1=0)


def test_rrf_overlapping_chunk_ranks_higher() -> None:
    result = reciprocal_rank_fusion(
        [["a", "b", "c"], ["b", "d", "a"]],
        k=60,
        limit=3,
    )
    assert result[0][0] in {"a", "b"}
    assert result[0][1] > result[-1][1]
    assert len(set(chunk_id for chunk_id, _ in result)) == len(result)


def test_rrf_deduplicates_single_branch() -> None:
    result = reciprocal_rank_fusion([["a", "a", "b"]], k=60, limit=5)
    assert [item[0] for item in result] == ["a", "b"]


def test_metadata_filter_enforces_uuid() -> None:
    assert _document_filter(None) is None
    with pytest.raises(ValueError):
        _document_filter("not-an-id")
    result = _document_filter("28eb0260-a5a5-4620-94fd-276b74a401f7")
    assert result is not None
