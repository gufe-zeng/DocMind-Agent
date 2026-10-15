"""M3a query_document_metadata tool: reads PostgreSQL document records."""

from typing import Any
from uuid import UUID

import asyncpg

from app.core.config import get_settings
from app.tools.registry import DocumentMetadataArgs


async def query_document_metadata(args: DocumentMetadataArgs) -> dict[str, Any]:
    settings = get_settings()
    document_uuid: UUID | None = None
    if args.document_id is not None:
        document_uuid = UUID(args.document_id)

    connection = await asyncpg.connect(settings.postgres_dsn, timeout=10)
    try:
        if document_uuid is None:
            rows = await connection.fetch(
                """
                SELECT id, filename, size_bytes, status, chunk_count, created_at
                  FROM documents ORDER BY created_at DESC LIMIT $1
                """,
                args.limit,
            )
        else:
            rows = await connection.fetch(
                """
                SELECT id, filename, size_bytes, status, chunk_count, created_at
                  FROM documents WHERE id = $1 LIMIT $2
                """,
                document_uuid,
                args.limit,
            )
    finally:
        await connection.close()

    documents = [
        {
            "document_id": str(row["id"]),
            "filename": row["filename"],
            "size_bytes": row["size_bytes"],
            "status": row["status"],
            "chunk_count": row["chunk_count"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
    return {
        "tool": "query_document_metadata",
        "status": "answered" if documents else "no_evidence",
        "documents": documents,
        "count": len(documents),
        "sources": [],
    }
