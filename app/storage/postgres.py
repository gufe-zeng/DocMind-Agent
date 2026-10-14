"""PostgreSQL adapter for M0 connectivity and M1 document metadata."""

from pathlib import Path
from uuid import UUID

import asyncpg


async def check_postgres(dsn: str) -> None:
    conn = await asyncpg.connect(dsn=dsn, timeout=3)
    try:
        if await conn.fetchval("SELECT 1") != 1:
            raise RuntimeError("Unexpected PostgreSQL health response.")
    finally:
        await conn.close()


async def init_documents_schema(dsn: str) -> None:
    """Apply a small, idempotent M1 migration during API startup."""
    migration = Path(__file__).resolve().parents[2] / "migrations" / "001_documents.sql"
    sql = migration.read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def add_document(
    dsn: str,
    *,
    document_id: UUID,
    filename: str,
    extension: str,
    size_bytes: int,
    sha256: str,
) -> None:
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        await conn.execute(
            """
            INSERT INTO documents (id, filename, extension, size_bytes, sha256)
            VALUES ($1, $2, $3, $4, $5)
            """,
            document_id, filename, extension, size_bytes, sha256,
        )
    finally:
        await conn.close()


def _record(row: asyncpg.Record | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


async def get_document(dsn: str, document_id: UUID) -> dict | None:
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, filename, extension, size_bytes, sha256,
                   status, chunk_count, embedding_model
            FROM documents WHERE id=$1
            """,
            document_id,
        )
        return _record(row)
    finally:
        await conn.close()


async def claim_indexing(dsn: str, document_id: UUID) -> dict | None:
    """Acquire a DB-backed indexing lease; stale leases are retryable after 1h."""
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        row = await conn.fetchrow(
            """
            UPDATE documents
               SET status='indexing', updated_at=NOW(), last_error=NULL
             WHERE id=$1
               AND (status <> 'indexing'
                    OR updated_at < NOW() - INTERVAL '1 hour')
            RETURNING id, filename, extension, size_bytes, sha256,
                      status, chunk_count, embedding_model
            """,
            document_id,
        )
        return _record(row)
    finally:
        await conn.close()


async def finish_indexing(
    dsn: str,
    document_id: UUID,
    *,
    status: str,
    chunk_count: int,
    embedding_model: str | None,
    error: str | None = None,
) -> None:
    if status not in ("indexed", "failed"):
        raise ValueError("Invalid terminal indexing status.")
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        await conn.execute(
            """
            UPDATE documents
               SET status=$2, chunk_count=$3, embedding_model=$4,
                   last_error=$5, updated_at=NOW()
             WHERE id=$1
            """,
            document_id, status, chunk_count, embedding_model, (error or "")[:500] or None,
        )
    finally:
        await conn.close()
