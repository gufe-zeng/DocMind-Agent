"""M4b source-of-truth Postgres memory + user-filtered Qdrant semantic recall.

Only an explicitly requested *contract output-format preference* is accepted.
Document chunks, raw conversation text, and unverified user facts must NOT be
promoted automatically into long-term memory.

This is a local demo: user_id is supplied by the client, not authenticated.
Never expose its API to an untrusted network without identity enforcement.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
import re
from uuid import UUID, NAMESPACE_URL, uuid5

import asyncpg
from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.rag.embedder import embed_texts


MEMORIES_COLLECTION = "memories_v1"
MEMORY_KEY = "contract_analysis_format"
MEMORY_TYPE = "preference"
SUPPORTED_FIELDS = ("主体", "金额", "期限", "风险", "引用")


@dataclass(frozen=True, slots=True)
class MemoryHit:
    id: str
    memory_type: str
    memory_key: str
    content: str
    score: float

    def public_dict(self) -> dict:
        return {
            "memory_id": self.id,
            "type": self.memory_type,
            "key": self.memory_key,
            "content": self.content,
            "score": round(self.score, 4),
        }


async def init_memory_schema(dsn: str) -> None:
    migration = Path(__file__).resolve().parents[2] / "migrations" / "002_memories.sql"
    sql = migration.read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def is_memory_command(query: str) -> bool:
    return bool(re.match(r"^\s*(?:请)?(?:帮我)?\s*(?:记住|记下|保存偏好)", query))


def parse_format_preference(query: str) -> tuple[str, ...]:
    """Extract only whitelisted category labels from an explicit command."""
    if not is_memory_command(query):
        raise ValueError("Long-term memory requires an explicit '记住' instruction.")
    if len(query) > 250 or not ("合同" in query or "文档" in query):
        raise ValueError("Only short document-analysis format preferences are supported.")
    if not any(word in query for word in ("输出", "格式", "按")):
        raise ValueError("Expected a document analysis output-format instruction.")
    positions = sorted(
        ((query.index(field), field) for field in SUPPORTED_FIELDS if field in query)
    )
    labels = tuple(field for _, field in positions)
    if len(labels) < 3:
        raise ValueError("Specify at least three supported output fields.")
    return labels


def preference_content(labels: tuple[str, ...]) -> str:
    if len(labels) < 3 or len(set(labels)) != len(labels):
        raise ValueError("Unsupported or duplicate preference labels.")
    if any(label not in SUPPORTED_FIELDS for label in labels):
        raise ValueError("Unsupported format field.")
    return "合同分析输出格式：" + "、".join(labels)


def _memory_uuid(user_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"docmind:memory:{user_id}:{MEMORY_KEY}")


class LongTermMemory:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _client(self) -> AsyncQdrantClient:
        return AsyncQdrantClient(
            url=self.settings.qdrant_url,
            api_key=self.settings.qdrant_api_key or None,
            timeout=60,
        )

    async def _vector(self, text: str) -> list[float]:
        vectors = await asyncio.to_thread(
            embed_texts,
            [text],
            model_name=self.settings.embedding_model,
            cache_dir=self.settings.embedding_cache_dir,
            expected_size=self.settings.embedding_vector_size,
        )
        return vectors[0]

    async def _ensure_collection(self, client: AsyncQdrantClient) -> None:
        if not await client.collection_exists(MEMORIES_COLLECTION):
            await client.create_collection(
                collection_name=MEMORIES_COLLECTION,
                vectors_config=models.VectorParams(
                    size=self.settings.embedding_vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
        existing = await client.get_collection(MEMORIES_COLLECTION)
        vector_config = existing.config.params.vectors
        if (
            not isinstance(vector_config, models.VectorParams)
            or vector_config.size != self.settings.embedding_vector_size
        ):
            raise RuntimeError("memories_v1 is not configured for 512D BGE vectors.")

    async def save_format(self, user_id: UUID, labels: tuple[str, ...]) -> dict:
        """Upsert explicit preference in PostgreSQL and Qdrant (retry-safe)."""
        text = preference_content(labels)
        memory_id = _memory_uuid(user_id)
        vector = await self._vector(text)

        # Mark unsynchronized before replacing the Qdrant vector. If the
        # vector write fails, the DB record remains visible for repair.
        conn = await asyncpg.connect(self.settings.postgres_dsn, timeout=10)
        try:
            await conn.execute(
                """
                INSERT INTO memories
                    (id, user_id, memory_type, memory_key, content, embedding_model, is_indexed)
                VALUES ($1, $2, $3, $4, $5, $6, FALSE)
                ON CONFLICT (user_id, memory_key)
                DO UPDATE SET content=EXCLUDED.content,
                              embedding_model=EXCLUDED.embedding_model,
                              is_indexed=FALSE, updated_at=NOW()
                """,
                memory_id, user_id, MEMORY_TYPE, MEMORY_KEY,
                text, self.settings.embedding_model,
            )
        finally:
            await conn.close()

        client = self._client()
        try:
            await self._ensure_collection(client)
            await client.upsert(
                collection_name=MEMORIES_COLLECTION,
                points=[
                    models.PointStruct(
                        id=str(memory_id),
                        vector=vector,
                        payload={
                            "user_id": str(user_id),
                            "memory_id": str(memory_id),
                            "memory_type": MEMORY_TYPE,
                            "memory_key": MEMORY_KEY,
                            "text": text,
                            "embedding_model": self.settings.embedding_model,
                        },
                    )
                ],
                wait=True,
            )
        finally:
            await client.close()

        conn = await asyncpg.connect(self.settings.postgres_dsn, timeout=10)
        try:
            await conn.execute(
                """
                UPDATE memories SET is_indexed=TRUE, updated_at=NOW()
                WHERE id=$1 AND user_id=$2 AND content=$3
                """,
                memory_id, user_id, text,
            )
        finally:
            await conn.close()
        return {
            "memory_id": str(memory_id),
            "type": MEMORY_TYPE,
            "key": MEMORY_KEY,
            "content": text,
        }

    async def search(self, user_id: UUID, query: str, *, limit: int = 3) -> list[MemoryHit]:
        """Cross-session semantic retrieval, with Qdrant AND PG user scopes."""
        if not query.strip() or limit < 1 or limit > 5:
            raise ValueError("Invalid memory recall query or limit.")
        client = self._client()
        try:
            if not await client.collection_exists(MEMORIES_COLLECTION):
                return []
            query_vector = await self._vector(query)
            result = await client.query_points(
                collection_name=MEMORIES_COLLECTION,
                query=query_vector,
                query_filter=models.Filter(must=[
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=str(user_id)),
                    ),
                    models.FieldCondition(
                        key="memory_type",
                        match=models.MatchValue(value=MEMORY_TYPE),
                    ),
                ]),
                limit=limit,
                with_payload=True,
            )
        finally:
            await client.close()

        if not result.points:
            return []
        # PostgreSQL is authoritative: only return persisted and indexed
        # records of the authenticated-scope *demo ID*; never trust a payload
        # to authorize cross-user memory access.
        conn = await asyncpg.connect(self.settings.postgres_dsn, timeout=10)
        try:
            ids = [UUID(str(point.id)) for point in result.points]
            rows = await conn.fetch(
                """
                SELECT id, memory_type, memory_key, content FROM memories
                WHERE user_id=$1 AND id=ANY($2::uuid[]) AND is_indexed=TRUE
                """,
                user_id, ids,
            )
        finally:
            await conn.close()
        approved = {str(row["id"]): row for row in rows}
        hits = []
        for point in result.points:
            row = approved.get(str(point.id))
            if row and (point.payload or {}).get("text") == row["content"]:
                hits.append(MemoryHit(
                    id=str(row["id"]),
                    memory_type=row["memory_type"],
                    memory_key=row["memory_key"],
                    content=row["content"],
                    score=float(point.score),
                ))
        return hits


def format_hint(hits: list[MemoryHit]) -> str | None:
    """Allow only stored, whitelisted format labels into model instructions."""
    for hit in hits:
        if hit.memory_type != MEMORY_TYPE or hit.memory_key != MEMORY_KEY:
            continue
        if not hit.content.startswith("合同分析输出格式："):
            continue
        fields = tuple(hit.content.split("：", 1)[1].split("、"))
        if len(fields) >= 3 and len(set(fields)) == len(fields):
            if all(field in SUPPORTED_FIELDS for field in fields):
                return "、".join(fields)
    return None
