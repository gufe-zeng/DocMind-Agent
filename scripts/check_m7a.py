"""M7a: upload/index synthetic documents, evaluate real unfiltered hybrid ranking."""
import asyncio
import json
from pathlib import Path

import httpx

from app.rag.retriever import hybrid_search
from eval.rag_metrics import RetrievalCase, evaluate_retrieval

FIXTURE = Path("/app/eval/datasets/m7a_retrieval.json")


async def main():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ids = {}
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False,
    ) as client:
        ready = await client.get("/health")
        ready.raise_for_status()
        for doc in fixture["documents"]:
            uploaded = await client.post(
                "/v1/documents",
                files={"file": (doc["filename"], doc["text"].encode("utf-8"), "text/plain")},
            )
            uploaded.raise_for_status()
            doc_id = uploaded.json()["document_id"]
            indexed = await client.post(f"/v1/documents/{doc_id}/index")
            indexed.raise_for_status()
            assert indexed.json()["status"] == "indexed"
            ids[doc["key"]] = doc_id

    # Qdrant is shared with prior smoke tests; only fixture document IDs count
    # toward this benchmark. Excluded non-fixture candidates are reported.
    fixture_ids = set(ids.values())
    cases = []
    out_of_fixture = 0
    for case in fixture["cases"]:
        hits = await hybrid_search(case["query"], top_k=100, candidate_k=100)
        out_of_fixture += sum(hit.document_id not in fixture_ids for hit in hits)
        ranked = tuple(dict.fromkeys(
            hit.document_id for hit in hits if hit.document_id in fixture_ids
        ))
        cases.append(RetrievalCase(
            case["query"], frozenset(ids[key] for key in case["gold"]), ranked,
        ))
    metrics = evaluate_retrieval(cases, k=3)
    metrics["candidate_chunks_outside_fixture"] = out_of_fixture
    metrics["dataset_version"] = fixture["version"]
    metrics["scope"] = "synthetic smoke benchmark, not generalization evidence"
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    assert metrics["recall_at_k"] == 1.0, "Synthetic document retrieval recall gate failed."
    print("M7a RETRIEVAL PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
