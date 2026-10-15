"""M2a integration smoke test: index documents and exercise both search branches.

The test uses synthetic documents and the already cached local CPU BGE model.
Expected final line: M2a PASS.
"""

import asyncio
from dataclasses import asdict
from uuid import uuid4

import httpx

from app.rag.retriever import hybrid_search


async def _index(client: httpx.AsyncClient, name: str, contents: str) -> str:
    response = await client.post(
        "/v1/documents",
        files={"file": (name, contents.encode("utf-8"), "text/plain")},
    )
    response.raise_for_status()
    doc_id = response.json()["document_id"]

    indexing = await client.post(f"/v1/documents/{doc_id}/index")
    indexing.raise_for_status()
    assert indexing.json()["status"] == "indexed"
    return doc_id


async def main() -> None:
    examples = [
        (
            "m2a_payment.txt",
            "合同付款期限：乙方服务验收合格后，甲方应当在三十日内完成付款。"
            "双方确认发票齐全后启动付款流程。",
        ),
        (
            "m2a_breach.txt",
            "违约责任：乙方延迟交付或者未履约，应按合同约定承担违约责任。"
            "争议解决方式为双方协商。",
        ),
        (
            "m2a_delivery.txt",
            "履约交付期限：服务应当在合同签订后六十日内完成，"
            "交付内容为工程技术报告。",
        ),
    ]

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        timeout=600,
        trust_env=False,
    ) as http:
        doc_ids: list[str] = []
        for filename, content in examples:
            identifier = await _index(http, filename, content)
            doc_ids.append(identifier)
            print(f"Indexed {filename}: {identifier}", flush=True)

    payment_id = doc_ids[0]
    filtered = await hybrid_search(
        "验收后付款期限三十日", document_id=payment_id, top_k=3
    )
    assert filtered, "No hybrid search evidence for indexed payment document."
    assert all(hit.document_id == payment_id for hit in filtered)
    assert filtered[0].filename == "m2a_payment.txt"
    assert filtered[0].chunk_id
    assert filtered[0].rrf_score > 0
    assert filtered[0].dense_rank is not None
    assert filtered[0].sparse_rank is not None
    print(
        "PASS document metadata filter + Dense/BM25/RRF:",
        asdict(filtered[0]),
        flush=True,
    )

    global_hits = await hybrid_search(
        "合同约定的付款时间是什么？", top_k=8, candidate_k=20
    )
    assert global_hits, "Global hybrid retrieval returned no evidence."
    assert any(hit.document_id and hit.chunk_id for hit in global_hits)
    print("Global ranking preview:", flush=True)
    for hit in global_hits[:5]:
        print(
            f"  {hit.filename} rrf={hit.rrf_score:.5f}"
            f" dense_rank={hit.dense_rank} sparse_rank={hit.sparse_rank}",
            flush=True,
        )

    empty = await hybrid_search(
        "付款期限", document_id=str(uuid4()), top_k=3
    )
    assert empty == [], "Nonexistent document filter must return no results."
    print("PASS nonexistent document filter returns empty evidence", flush=True)

    print("M2a PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
