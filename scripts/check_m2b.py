"""M2b end-to-end smoke test: real RAG retrieval/reranking, mock or live LLM.

Default runs genuine retrieval and CPU BGE reranking with an injected
deterministic LLM stub, verifying the citation contract without requiring vLLM.
--live exercises the configured OpenAI-compatible endpoint; it must be running.
"""

import argparse
import asyncio

import httpx

from app.core.config import get_settings
from app.llm.client import LLMResult
from app.rag import pipeline
from app.rag.pipeline import answer_document_question, answer_to_dict


DOCUMENT = (
    "测试合同付款约定：乙方完成服务并经甲方验收合格后，甲方应在"
    "三十日内支付合同款项。双方确认已收到完整发票后付款。"
)


async def upload_and_index() -> str:
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False
    ) as client:
        uploaded = await client.post(
            "/v1/documents",
            files={"file": ("m2b_payment.txt", DOCUMENT.encode(), "text/plain")},
        )
        uploaded.raise_for_status()
        doc_id = uploaded.json()["document_id"]
        indexing = await client.post(f"/v1/documents/{doc_id}/index")
        indexing.raise_for_status()
        assert indexing.json()["status"] == "indexed"
        print(f"Indexed evidence: {doc_id}", flush=True)
        return doc_id


async def main(live: bool) -> None:
    settings = get_settings()
    document_id = await upload_and_index()
    question = "根据合同，服务验收后付款期限是多少天？"

    if not live:
        async def mock_completion(messages, **kwargs):
            assert "[S1]" in messages[1]["content"]
            return LLMResult(
                text="服务验收合格后三十日内完成付款。[S1]",
                prompt_tokens=123,
                completion_tokens=29,
            )
        pipeline.complete_chat = mock_completion

    result = await answer_document_question(question, document_id=document_id)
    outcome = answer_to_dict(result)
    print(f"Status: {outcome['status']}", flush=True)
    print(f"Answer: {outcome['answer']}", flush=True)
    for source in outcome["sources"]:
        print(
            f"  [{source['id']}] {source['filename']} "
            f"page={source['page']} chunk_id={source['chunk_id']}",
            flush=True,
        )
    assert result.citation_valid, outcome
    assert result.status == "answered", outcome
    assert result.citations_used, outcome
    assert result.sources[0].document_id == document_id, outcome

    if live:
        print(
            f"LLM endpoint: {settings.llm_base_url}, model: {settings.llm_model}",
            flush=True,
        )
        print("M2b LIVE PASS", flush=True)
    else:
        print("M2b core PASS (deterministic mock LLM)", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Call configured vLLM")
    args = parser.parse_args()
    asyncio.run(main(args.live))
