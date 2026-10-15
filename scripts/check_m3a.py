"""M3a end-to-end: upload -> index -> LangGraph tools -> cited Qwen reply.

Requires the DocMind-Agent Docker stack and a live llm-serving-ops vLLM
endpoint on host port 8000. Existing embedding/reranker caches are reused.
"""

import asyncio
import httpx


async def main() -> None:
    source = (
        "合同甲方：甲方示例科技有限公司。乙方：乙方示例服务有限公司。"
        "付款条款：乙方完成服务并通过甲方验收后，甲方应在三十日内支付款项。"
        "违约责任：任何一方未履行义务，应按照合同约定承担违约责任。"
    )
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        timeout=600,
        trust_env=False,
    ) as client:
        up = await client.post(
            "/v1/documents",
            files={"file": ("m3a_contract.txt", source.encode("utf-8"), "text/plain")},
        )
        up.raise_for_status()
        document_id = up.json()["document_id"]

        index = await client.post(f"/v1/documents/{document_id}/index")
        index.raise_for_status()
        print("Indexed:", document_id, flush=True)

        metadata = await client.post(
            "/v1/chat",
            json={"query": "列出已上传的文档", "document_id": document_id},
        )
        metadata.raise_for_status()
        metadata_result = metadata.json()
        assert metadata_result["status"] == "answered", metadata_result
        assert metadata_result["tools_called"] == ["query_document_metadata"]
        assert metadata_result["steps"] == 1
        assert "m3a_contract.txt" in metadata_result["answer"]
        print("PASS LangGraph metadata tool:", metadata_result["answer"], flush=True)

        qa = await client.post(
            "/v1/chat",
            json={
                "query": "根据合同，验收后付款期限是多少天？",
                "document_id": document_id,
            },
        )
        qa.raise_for_status()
        answer = qa.json()
        print("Agent answer:", answer["answer"], flush=True)
        print("Tools called:", answer["tools_called"], flush=True)
        for source_row in answer["sources"]:
            print(
                f"  [{source_row['id']}] "
                f"{source_row['filename']} chunk={source_row['chunk_id']}",
                flush=True,
            )
        assert answer["status"] == "answered", answer
        assert answer["tools_called"] == ["search_documents"]
        assert answer["steps"] == 1
        assert "[S1]" in answer["answer"]
        assert answer["sources"], answer
        assert all(s["document_id"] == document_id for s in answer["sources"])
        print("PASS LangGraph RAG Tool + real Qwen citation", flush=True)

    print("M3a PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
