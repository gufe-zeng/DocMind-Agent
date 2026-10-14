"""Qdrant adapter for health, durable chunk vectors and provenance payload."""

from qdrant_client import AsyncQdrantClient, models

from app.rag.chunker import DocumentChunk


DOCUMENTS_COLLECTION = "documents_v1"


async def check_qdrant(url: str, api_key: str | None = None) -> None:
    client = AsyncQdrantClient(url=url, api_key=api_key or None, timeout=3)
    try:
        await client.get_collections()
    finally:
        await client.close()


def _filter_document(document_id: str) -> models.Filter:
    return models.Filter(
        must=[
            models.FieldCondition(
                key="document_id",
                match=models.MatchValue(value=document_id),
            )
        ]
    )


def build_points(
    chunks: list[DocumentChunk],
    vectors: list[list[float]],
    model_name: str,
) -> list[models.PointStruct]:
    """Build deterministic point IDs and citation-compatible payloads."""
    if len(chunks) != len(vectors):
        raise ValueError("Chunks and vectors counts do not match.")

    return [
        models.PointStruct(
            id=chunk.chunk_id,
            vector=vector,
            payload={
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "chunk_id": chunk.chunk_id,
                "chunk_index": chunk.chunk_index,
                "page": chunk.page,
                "section": chunk.section,
                "source_block_index": chunk.source_block_index,
                "start_offset": chunk.start_offset,
                "end_offset": chunk.end_offset,
                "text": chunk.text,
                "embedding_model": model_name,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]


async def store_document_vectors(
    *,
    url: str,
    api_key: str | None,
    document_id: str,
    chunks: list[DocumentChunk],
    vectors: list[list[float]],
    model_name: str,
    vector_size: int,
) -> int:
    if not chunks:
        raise ValueError("Cannot index a document without chunks.")
    if any(len(v) != vector_size for v in vectors):
        raise ValueError("Embedding dimension mismatch.")

    client = AsyncQdrantClient(url=url, api_key=api_key or None, timeout=60)
    try:
        if not await client.collection_exists(DOCUMENTS_COLLECTION):
            await client.create_collection(
                collection_name=DOCUMENTS_COLLECTION,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                ),
            )

        info = await client.get_collection(DOCUMENTS_COLLECTION)
        config = info.config.params.vectors
        if not isinstance(config, models.VectorParams) or config.size != vector_size:
            raise RuntimeError(
                f"{DOCUMENTS_COLLECTION} vector configuration is not "
                f"the expected {vector_size}-dimensional unnamed vector."
            )

        # Replacement semantics: remove stale points from earlier indexing runs.
        await client.delete(
            collection_name=DOCUMENTS_COLLECTION,
            points_selector=models.FilterSelector(
                filter=_filter_document(document_id),
            ),
            wait=True,
        )
        await client.upsert(
            collection_name=DOCUMENTS_COLLECTION,
            points=build_points(chunks, vectors, model_name),
            wait=True,
        )
        result = await client.count(
            collection_name=DOCUMENTS_COLLECTION,
            count_filter=_filter_document(document_id),
            exact=True,
        )
        if result.count != len(chunks):
            raise RuntimeError(
                f"Qdrant stored {result.count} points; expected {len(chunks)}."
            )
        return result.count
    finally:
        await client.close()
