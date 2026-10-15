"""M3a search_documents tool: delegates to the accepted M2 RAG pipeline."""

from typing import Any

from app.rag.pipeline import answer_document_question, answer_to_dict
from app.tools.registry import SearchDocumentsArgs


async def search_documents(args: SearchDocumentsArgs) -> dict[str, Any]:
    answer = await answer_document_question(
        args.query, document_id=args.document_id
    )
    payload = answer_to_dict(answer)
    return {
        "tool": "search_documents",
        "status": payload["status"],
        "answer": payload["answer"],
        "sources": payload["sources"],
        "citations_used": payload["citations_used"],
        "retrieved_candidates": payload["retrieved_candidates"],
    }
