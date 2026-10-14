"""Unit checks for document upload safety and source-aware Qdrant payloads."""

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastembed import TextEmbedding

from app.api.documents import _write_document, safe_filename
from app.rag.chunker import DocumentChunk
from app.storage.qdrant import build_points


def test_sanitize_uploaded_filename() -> None:
    assert safe_filename(r"C:\\tmp\\contract.pdf") == "contract.pdf"
    assert safe_filename("../contract.docx") == "contract.docx"
    assert safe_filename("contract.TXT") == "contract.TXT"
    with pytest.raises(HTTPException) as exc:
        safe_filename("script.exe")
    assert exc.value.status_code == 415


def test_atomic_document_write(tmp_path: Path) -> None:
    target = tmp_path / "data" / "stored.txt"
    _write_document(target, b"example")
    assert target.read_bytes() == b"example"
    assert not target.with_suffix(".txt.tmp").exists()


def test_point_payload_preserves_source() -> None:
    chunk_id = str(uuid4())
    chunk = DocumentChunk(
        chunk_id=chunk_id,
        document_id=str(uuid4()),
        filename="test.pdf",
        page=3,
        section=None,
        text="付款期限为三十日。",
        chunk_index=0,
        source_block_index=2,
        start_offset=0,
        end_offset=10,
    )
    point = build_points(
        [chunk],
        [[0.1] * 512],
        "BAAI/bge-small-zh-v1.5",
    )[0]
    assert str(point.id) == chunk_id
    assert point.payload["page"] == 3
    assert point.payload["text"] == "付款期限为三十日。"
    assert point.payload["document_id"] == chunk.document_id


def test_chinese_embedding_is_supported() -> None:
    names = {model["model"]: model for model in TextEmbedding.list_supported_models()}
    assert names["BAAI/bge-small-zh-v1.5"]["dim"] == 512
