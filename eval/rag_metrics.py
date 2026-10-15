"""Pure, deterministic ranking and citation-provenance metrics for M7a."""
from dataclasses import dataclass
from statistics import mean

from app.rag.citation import validate_answer_citations


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    expected_document_ids: frozenset[str]
    ranked_document_ids: tuple[str, ...]


def evaluate_retrieval(cases: list[RetrievalCase], *, k: int = 5) -> dict:
    if not cases or k <= 0:
        raise ValueError("Nonempty cases and positive k required.")
    if any(not x.expected_document_ids for x in cases):
        raise ValueError("Each case needs nonempty gold documents.")

    recalls = []
    reciprocal_ranks = []
    for case in cases:
        top = case.ranked_document_ids[:k]
        found = case.expected_document_ids.intersection(top)
        recalls.append(len(found) / len(case.expected_document_ids))
        rank = next(
            (index for index, item in enumerate(top, 1)
             if item in case.expected_document_ids),
            None,
        )
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    return {
        "cases": len(cases),
        "k": k,
        "recall_at_k": mean(recalls),
        "mrr_at_k": mean(reciprocal_ranks),
        "evaluation_unit": "document",
    }


def citation_provenance_accuracy(examples: list[tuple[str, list]]) -> dict:
    """Valid source identifiers only; NOT semantic correctness of cited claims."""
    if not examples:
        raise ValueError("Nonempty citation examples required.")
    passed = sum(
        validate_answer_citations(answer, sources).valid
        for answer, sources in examples
    )
    return {
        "cases": len(examples),
        "citation_provenance_accuracy": passed / len(examples),
        "checks_semantic_entailment": False,
    }
