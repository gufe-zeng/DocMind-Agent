"""M3b document-focused summary with the verified M2 evidence pipeline.

This tool summarizes *retrieved evidence*, not necessarily every page of a
long document. It explicitly labels the scope instead of pretending to have
read the entire file. Qwen answers must pass M2 citation-ID checks.
"""

from typing import Any

from app.rag.pipeline import answer_document_question, answer_to_dict
from app.tools.registry import SummarizeDocumentArgs


async def summarize_document(args: SummarizeDocumentArgs) -> dict[str, Any]:
    focus = (
        "请根据指定文档的可检索证据，简要总结能够确认的主体、付款条件、"
        "履约义务和违约责任。不得推测未覆盖的部分。"
        f"用户要求：{args.query}"
    )
    result = answer_to_dict(
        await answer_document_question(focus, document_id=str(args.document_id))
    )
    scope = "retrieved_evidence_only"
    return {
        "tool": "summarize_document",
        "status": result["status"],
        "answer": (
            "基于检索片段的摘要（不代表全文覆盖）：\n" + result["answer"]
            if result["status"] == "answered"
            else result["answer"]
        ),
        "summary_scope": scope,
        "citations_used": result["citations_used"],
        "sources": result["sources"],
        "retrieved_candidates": result["retrieved_candidates"],
    }
