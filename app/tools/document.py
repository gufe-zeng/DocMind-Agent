"""Read source-anchored chunks for one indexed document via Qdrant.

M3b extraction needs precise source text, not a generated RAG answer.
Reads are bounded and never silently truncate the document scan.
"""

from uuid import UUID

from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from app.storage.qdrant import DOCUMENTS_COLLECTION, _filter_document


async def load_document_chunks(
    document_id: str, *, max_chunks: int = 200
) -> list[dict]:
    """Return indexed source payloads in their original chunk order."""
    normalized_id = str(UUID(document_id))
    if not 0 < max_chunks <= 1000:
        raise ValueError("max_chunks must be between 1 and 1000")

    settings = get_settings()
    client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
        timeout=30,
    )
    try:
        if not await client.collection_exists(DOCUMENTS_COLLECTION):
            return []
        offset = None
        chunks: list[dict] = []
        while True:
            points, next_offset = await client.scroll(
                collection_name=DOCUMENTS_COLLECTION,
                scroll_filter=_filter_document(normalized_id),
                offset=offset,
                limit=64,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                payload = dict(point.payload or {})
                if not payload.get("text") or not payload.get("chunk_id"):
                    continue
                chunks.append(payload)
                if len(chunks) > max_chunks:
                    raise RuntimeError(
                        "Document exceeds M3b source scan limit; no partial "
                        "document extraction is returned."
                    )
            if next_offset is None:
                break
            offset = next_offset
        return sorted(chunks, key=lambda row: int(row.get("chunk_index", 0)))
    finally:
        await client.close()
