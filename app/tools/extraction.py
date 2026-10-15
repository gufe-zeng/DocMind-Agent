"""M3b deterministic legal-document entity/term extraction.

Extracts limited supported facts from actual indexed source text. It does not
ask an LLM to invent parties or deadlines, and returns a citation per fact.
Patterns are a baseline and are not equivalent to general-purpose legal NER.
"""

import re
from typing import Any

from app.tools.document import load_document_chunks
from app.tools.registry import ExtractEntitiesArgs


PARTY_PATTERN = re.compile(
    r"(?P<role>甲方|乙方|丙方)\s*[:：]\s*"
    r"(?P<name>[^，。；;\n]{2,60})"
)
TERM_PATTERN = re.compile(
    r"(?P<term>(?:\d{1,4}|[一二两三四五六七八九十百零〇]+)"
    r"(?:个)?(?:工作)?(?:日|天|月|年))"
)


def _excerpt(text: str, start: int, end: int, *, width: int = 160) -> str:
    """Return a source substring anchored around the actual match."""
    start_at = max(0, start - 45)
    end_at = min(len(text), max(end + 45, start_at + width))
    if end_at - start_at > width:
        end_at = min(len(text), start_at + width)
    return text[start_at:end_at]


def _candidate_facts(text: str) -> list[tuple[str, str, int, int]]:
    candidates: list[tuple[str, str, int, int]] = []
    for match in PARTY_PATTERN.finditer(text):
        candidates.append(
            (match.group("role"), match.group("name").strip(), *match.span())
        )
    # Terms are only classified as payment-related when the same clause
    # contains an explicit payment verb, avoiding unsupported role inference.
    start = 0
    for clause in re.finditer(r"[^。；;\n]+", text):
        sentence = clause.group()
        if not ("付款" in sentence or "支付" in sentence or "结算" in sentence):
            continue
        term = TERM_PATTERN.search(sentence)
        if term:
            candidates.append(
                (
                    "付款期限",
                    term.group("term"),
                    clause.start() + term.start(),
                    clause.start() + term.end(),
                )
            )
    return sorted(candidates, key=lambda item: item[2])


async def extract_entities(args: ExtractEntitiesArgs) -> dict[str, Any]:
    """Return supported fields with evidence references, no LLM call."""
    chunks = await load_document_chunks(str(args.document_id), max_chunks=200)
    sources: list[dict[str, Any]] = []
    entities: list[dict[str, Any]] = []
    seen_fields: set[str] = set()

    for chunk in chunks:
        text = str(chunk["text"])
        for field, value, start, end in _candidate_facts(text):
            if field in seen_fields or len(entities) >= 10:
                continue
            seen_fields.add(field)
            source_id = f"S{len(sources) + 1}"
            sources.append(
                {
                    "id": source_id,
                    "document_id": str(chunk["document_id"]),
                    "chunk_id": str(chunk["chunk_id"]),
                    "filename": str(chunk["filename"]),
                    "page": chunk.get("page"),
                    "section": chunk.get("section"),
                    "evidence": _excerpt(text, start, end),
                }
            )
            entities.append(
                {
                    "field": field,
                    "value": value,
                    "source_id": source_id,
                    "chunk_id": str(chunk["chunk_id"]),
                }
            )

    answer = "\n".join(
        f"{entity['field']}：{entity['value']} [{entity['source_id']}]"
        for entity in entities
    )
    return {
        "tool": "extract_entities",
        "status": "answered" if entities else "no_evidence",
        "answer": answer or "未在该文档中匹配到当前规则支持的主体或付款期限。",
        "entities": entities,
        "sources": sources,
    }
