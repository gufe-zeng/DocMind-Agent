"""Pure M7a metric regression tests; no Docker, model or Qdrant needed."""
import pytest

from eval.rag_metrics import RetrievalCase, evaluate_retrieval, citation_provenance_accuracy
from app.rag.citation import EvidenceSource


def test_recall_mrr_and_truncation():
    cases = [
        RetrievalCase("a", frozenset({"gold"}), ("wrong", "gold", "other")),
        RetrievalCase("b", frozenset({"absent"}), ("wrong", "other")),
    ]
    assert evaluate_retrieval(cases, k=2) == {
        "cases": 2, "k": 2, "recall_at_k": 0.5,
        "mrr_at_k": 0.25, "evaluation_unit": "document",
    }
    assert evaluate_retrieval(cases, k=1)["recall_at_k"] == 0


def test_multi_gold_recall():
    case = RetrievalCase("a", frozenset({"a", "b"}), ("a", "x", "b"))
    metrics = evaluate_retrieval([case], k=2)
    assert metrics["recall_at_k"] == 0.5
    assert metrics["mrr_at_k"] == 1


def test_invalid_gold_or_k():
    with pytest.raises(ValueError):
        evaluate_retrieval([])
    with pytest.raises(ValueError):
        evaluate_retrieval([RetrievalCase("q", frozenset(), ())])


def test_citation_provenance_is_not_faithfulness():
    src = EvidenceSource("S1", "doc", "chunk", "file", None, None, "evidence", 0.1)
    scores = citation_provenance_accuracy([
        ("事实。[S1]", [src]),
        ("伪造引用。[S7]", [src]),
        ("没有引用", [src]),
    ])
    assert scores["citation_provenance_accuracy"] == pytest.approx(1 / 3)
    assert scores["checks_semantic_entailment"] is False
