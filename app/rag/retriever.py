"""M2a: bounded hybrid retrieval over previously indexed Qdrant chunks.

Branches:
  1. Dense: BGE-small-zh-v1.5 query embedding + Qdrant cosine search.
  2. Sparse: Chinese character-bigram BM25 over stored text payloads.
  3. Fusion: RRF, using ranks rather than incomparable branch scores.

In this educational checkpoint, BM25 reads a bounded corpus via Qdrant
scroll. This is suitable for the small V1 test corpus but is not intended
as a production-scale sparse index. Never silently truncate scan results.
"""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.rag.embedder import embed_texts
from app.rag.fusion import reciprocal_rank_fusion
from app.rag.sparse import bm25_rank
from app.storage.qdrant import DOCUMENTS_COLLECTION
from app.observability.tracing import timed_retrieval


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    document_id: str
    chunk_id: str
    filename: str
    page: int | None
    section: str | None
    text: str
    rrf_score: float
    dense_rank: int | None
    sparse_rank: int | None


def _document_filter(document_id: str | None) -> models.Filter | None:
    if document_id is None:
        return None
    try:
        normalized = str(UUID(document_id))
    except ValueError as exc:
        raise ValueError("document_id must be a UUID.") from exc
    return models.Filter(
        must=[
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=normalized),
            )
        ]
    )


async def _read_corpus(
    client: AsyncQdrantClient,
    *,
    query_filter: models.Filter | None,
    max_chunks: int,
) -> dict[str, dict]:
    """Read the entire bounded candidate corpus, without vectors."""
    corpus: dict[str, dict] = {}
    offset = None

    while True:
        points, next_offset = await client.scroll(
            collection_name=DOCUMENTS_COLLECTION,
            scroll_filter=query_filter,
            with_payload=True,
            with_vectors=False,
            limit=128,
            offset=offset,
        )
        for point in points:
            payload = point.payload or {}
            chunk_id = str(payload.get("chunk_id") or point.id)
            if not isinstance(payload.get("text"), str) or not payload["text"]:
                continue
            corpus[chunk_id] = payload
            if len(corpus) > max_chunks:
                raise RuntimeError(
                    "M2a BM25 scan exceeded max_chunks. "
                    "Use a dedicated indexed sparse retrieval backend."
                )
        if next_offset is None:
            break
        offset = next_offset
    return corpus


@timed_retrieval
async def hybrid_search(
    query: str,
    *,
    document_id: str | None = None,
    top_k: int = 5,
    candidate_k: int = 20,
    max_scan_chunks: int = 5000,
) -> list[RetrievalHit]:
    """Return RRF-ranked, source-anchored evidence from both retrieval branches."""
    if not query.strip():
        raise ValueError("Query cannot be empty.")
    if len(query) > 2000:
        raise ValueError("Query is too long.")
    if not (0 < top_k <= candidate_k <= 100):
        raise ValueError("Require 0 < top_k <= candidate_k <= 100.")
    if max_scan_chunks <= 0:
        raise ValueError("max_scan_chunks must be positive.")

    settings = get_settings()
    query_filter = _document_filter(document_id)
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )
    try:
        if not await client.collection_exists(DOCUMENTS_COLLECTION):
            return []

        payloads = await _read_corpus(
            client, query_filter=query_filter, max_chunks=max_scan_chunks
        )
        if not payloads:
            return []

        vector = (
            await asyncio.to_thread(
                embed_texts,
                [query],
                model_name=settings.embedding_model,
                cache_dir=settings.embedding_cache_dir,
                expected_size=settings.embedding_vector_size,
            )
        )[0]
        dense_response = await client.query_points(
            collection_name=DOCUMENTS_COLLECTION,
            query=vector,
            query_filter=query_filter,
            with_payload=True,
            limit=candidate_k,
        )

        dense_ids: list[str] = []
        for point in dense_response.points:
            payload = point.payload or {}
            chunk_id = str(payload.get("chunk_id") or point.id)
            if chunk_id in payloads:
                dense_ids.append(chunk_id)

        sparse_scores = bm25_rank(
            query,
            {chunk_id: payload["text"] for chunk_id, payload in payloads.items()},
            limit=candidate_k,
        )
        sparse_ids = [chunk_id for chunk_id, _ in sparse_scores]
        dense_ranks = {chunk_id: index + 1 for index, chunk_id in enumerate(dense_ids)}
        sparse_ranks = {chunk_id: index + 1 for index, chunk_id in enumerate(sparse_ids)}

        fused = reciprocal_rank_fusion(
            [dense_ids, sparse_ids], k=60, limit=top_k
        )
        return [
            RetrievalHit(
                document_id=str(payloads[chunk_id]["document_id"]),
                chunk_id=chunk_id,
                filename=str(payloads[chunk_id]["filename"]),
                page=payloads[chunk_id].get("page"),
                section=payloads[chunk_id].get("section"),
                text=str(payloads[chunk_id]["text"]),
                rrf_score=score,
                dense_rank=dense_ranks.get(chunk_id),
                sparse_rank=sparse_ranks.get(chunk_id),
            )
            for chunk_id, score in fused
        ]
    finally:
        await client.close()
