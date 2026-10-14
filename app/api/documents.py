"""M1b: document upload and indexing endpoints.

The API intentionally separates durable upload from CPU embedding/indexing,
so an indexing failure does not discard the original source document.
"""

import asyncio
import hashlib
import logging
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.rag.chunker import chunk_document
from app.rag.embedder import embed_texts
from app.rag.parser import SUPPORTED_EXTENSIONS, parse_document
from app.storage.postgres import (
    add_document,
    claim_indexing,
    finish_indexing,
    get_document,
)
from app.storage.qdrant import store_document_vectors


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/documents", tags=["documents"])


def safe_filename(name: str | None) -> str:
    """Strip Windows and POSIX path components from untrusted filenames."""
    filename = (name or "").replace("\\", "/").split("/")[-1].strip()
    if not filename or len(filename) > 255 or "\x00" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")
    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only PDF, DOCX and TXT are supported.")
    return filename


def _write_document(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_bytes(data)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(file: UploadFile = File(...)) -> dict:
    settings = get_settings()
    filename = safe_filename(file.filename)
    extension = Path(filename).suffix.lower()

    content = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty.")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Document exceeds 10 MiB limit.")

    # Validate content once before committing durable metadata.
    try:
        await asyncio.to_thread(parse_document, filename, content)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Document has no usable text or is invalid ({type(exc).__name__}).",
        ) from exc

    document_id = uuid4()
    path = Path(settings.upload_dir) / f"{document_id}{extension}"
    try:
        await asyncio.to_thread(_write_document, path, content)
        await add_document(
            settings.postgres_dsn,
            document_id=document_id,
            filename=filename,
            extension=extension,
            size_bytes=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        )
    except Exception as exc:
        path.unlink(missing_ok=True)
        logger.exception("Failed to persist uploaded document %s", document_id)
        raise HTTPException(status_code=503, detail="Document storage is unavailable.") from exc

    return {
        "document_id": str(document_id),
        "filename": filename,
        "size_bytes": len(content),
        "status": "uploaded",
    }


@router.post("/{document_id}/index")
async def index_document(document_id: UUID) -> dict:
    settings = get_settings()

    claimed = await claim_indexing(settings.postgres_dsn, document_id)
    if claimed is None:
        existing = await get_document(settings.postgres_dsn, document_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        raise HTTPException(status_code=409, detail="Document is already being indexed.")

    try:
        path = Path(settings.upload_dir) / f"{document_id}{claimed['extension']}"
        content = await asyncio.to_thread(path.read_bytes)
        blocks = await asyncio.to_thread(parse_document, claimed["filename"], content)
        chunks = chunk_document(str(document_id), claimed["filename"], blocks)
        if len(chunks) > settings.max_chunks_per_document:
            raise ValueError("Document produces too many chunks for V1 ingestion.")

        vectors = await asyncio.to_thread(
            embed_texts,
            [chunk.text for chunk in chunks],
            model_name=settings.embedding_model,
            cache_dir=settings.embedding_cache_dir,
            expected_size=settings.embedding_vector_size,
        )
        count = await store_document_vectors(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            document_id=str(document_id),
            chunks=chunks,
            vectors=vectors,
            model_name=settings.embedding_model,
            vector_size=settings.embedding_vector_size,
        )

        await finish_indexing(
            settings.postgres_dsn,
            document_id,
            status="indexed",
            chunk_count=count,
            embedding_model=settings.embedding_model,
        )
        return {
            "document_id": str(document_id),
            "status": "indexed",
            "chunk_count": count,
            "embedding_model": settings.embedding_model,
            "vector_size": settings.embedding_vector_size,
        }
    except ValueError as exc:
        await finish_indexing(
            settings.postgres_dsn,
            document_id,
            status="failed",
            chunk_count=0,
            embedding_model=settings.embedding_model,
            error=str(exc),
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Indexing failed for %s", document_id)
        await finish_indexing(
            settings.postgres_dsn,
            document_id,
            status="failed",
            chunk_count=0,
            embedding_model=settings.embedding_model,
            error=f"{type(exc).__name__}: {str(exc)[:300]}",
        )
        raise HTTPException(
            status_code=503,
            detail="Indexing failed. Inspect 'docker compose logs api'.",
        ) from exc
