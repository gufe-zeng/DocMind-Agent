"""M1a: PDF/DOCX/TXT parsing with source metadata.

PDF pages are 1-based. DOCX/TXT have no reliable physical page numbers,
so page=None; DOCX heading titles are kept in section metadata.
"""

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re

import pymupdf
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".txt"})


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    text: str
    page: int | None = None
    section: str | None = None


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[ \t]*\n[ \t]*", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _parse_pdf(data: bytes) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    with pymupdf.open(stream=data, filetype="pdf") as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = normalize_text(page.get_text("text", sort=True))
            if text:
                blocks.append(ParsedBlock(text=text, page=page_number))
    return blocks


def _parse_docx(data: bytes) -> list[ParsedBlock]:
    document = Document(BytesIO(data))
    blocks: list[ParsedBlock] = []
    section: str | None = None
    lines: list[str] = []

    def flush() -> None:
        text = normalize_text("\n".join(lines))
        if text:
            blocks.append(ParsedBlock(text=text, section=section))
        lines.clear()

    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            text = normalize_text(item.text)
            if not text:
                continue
            style = getattr(item.style, "name", "") or ""
            if style.lower().startswith("heading") or style.startswith("标题"):
                flush()
                section = text
            else:
                lines.append(text)
        elif isinstance(item, Table):
            for row in item.rows:
                cells = [normalize_text(cell.text) for cell in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))

    flush()
    return blocks


def _parse_txt(data: bytes) -> list[ParsedBlock]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("gb18030")
    text = normalize_text(text)
    return [ParsedBlock(text=text)] if text else []


def parse_document(filename: str, data: bytes) -> list[ParsedBlock]:
    if not data:
        raise ValueError("Document is empty.")
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {extension or '(none)'}")

    if extension == ".pdf":
        blocks = _parse_pdf(data)
    elif extension == ".docx":
        blocks = _parse_docx(data)
    else:
        blocks = _parse_txt(data)

    if not blocks:
        raise ValueError("No extractable text; scanned PDFs require OCR (not in V1).")
    return blocks
