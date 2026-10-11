"""M1a: deterministic chunks that preserve source-page boundaries."""

from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from app.rag.parser import ParsedBlock


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    filename: str
    page: int | None
    section: str | None
    text: str
    chunk_index: int
    source_block_index: int
    start_offset: int
    end_offset: int


def chunk_document(
    document_id: str,
    filename: str,
    blocks: list[ParsedBlock],
    *,
    chunk_size: int = 400,
    overlap: int = 60,
) -> list[DocumentChunk]:
    """Split source blocks; never create a chunk spanning two PDF pages."""
    if chunk_size <= 0 or not (0 <= overlap < chunk_size // 2):
        raise ValueError("Require chunk_size > 0 and 0 <= overlap < chunk_size / 2.")

    chunks: list[DocumentChunk] = []
    for block_index, block in enumerate(blocks):
        source = block.text
        start = 0
        while start < len(source):
            limit = min(start + chunk_size, len(source))
            end = limit

            if limit < len(source):
                preferred = max(
                    source.rfind(mark, start + chunk_size // 2, limit)
                    for mark in ("\n", "。", "！", "？", "；", ".", ";")
                )
                if preferred >= 0:
                    end = preferred + 1

            segment = source[start:end].strip()
            if segment:
                chunk_uid = uuid5(
                    NAMESPACE_URL, f"{document_id}:{block_index}:{start}:{end}"
                )
                chunks.append(
                    DocumentChunk(
                        chunk_id=str(chunk_uid),
                        document_id=document_id,
                        filename=filename,
                        page=block.page,
                        section=block.section,
                        text=segment,
                        chunk_index=len(chunks),
                        source_block_index=block_index,
                        start_offset=start,
                        end_offset=end,
                    )
                )

            if end == len(source):
                break
            start = end - overlap

    return chunks
