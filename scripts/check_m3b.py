"""M3b live integration: entities, scoped summary and bounded tool planning.

Requires Qdrant, PostgreSQL, CPU ONNX cache, and a running Qwen3 vLLM at
host.docker.internal:8000/v1. It makes no new model downloads.
"""

import asyncio

import httpx


CONTRACT = (
    "甲方：甲方示例科技有限公司。\n"
    "乙方：乙方示例服务有限公司。\n"
    "付款条款：乙方完成服务并通过甲方验收后，甲方应在三十日内支付合同款项。\n"
    "违约责任：任何一方未按约定履行义务，应承担合同规定的违约责任。"
)


def assert_citations_match_sources(payload: dict) -> None:
    source_ids = [source["id"] for source in payload["sources"]]
    assert len(source_ids) == len(set(source_ids)), "Source IDs must be unique"
    for entity in payload["entities"]:
        assert entity["source_id"] in source_ids, entity
    for source_id in source_ids:
        assert source_id.startswith("S")


async def call_chat(client, query, document_id):
    response = await client.post(
        "/v1/chat",
        json={"query": query, "document_id": document_id},
    )
    if response.status_code != 200:
        print("Chat error:", response.status_code, response.text[:1000], flush=True)
    response.raise_for_status()
    result = response.json()
    print(
        f"query={query}\n"
        f"plan_source={result['plan_source']} "
        f"tools={result['tools_called']} status={result['status']}\n"
        f"answer={result['answer']}",
        flush=True,
    )
    assert_citations_match_sources(result)
    return result


async def main():
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        timeout=600,
        trust_env=False,
    ) as client:
        upload = await client.post(
            "/v1/documents",
            files={"file": ("m3b_contract.txt", CONTRACT.encode("utf-8"), "text/plain")},
        )
        upload.raise_for_status()
        doc_id = upload.json()["document_id"]

        index = await client.post(f"/v1/documents/{doc_id}/index")
        index.raise_for_status()
        print("Indexed:", doc_id, flush=True)

        extracted = await call_chat(
            client, "提取甲乙方及付款期限", doc_id
        )
        assert extracted["status"] == "answered", extracted
        assert extracted["tools_called"] == ["extract_entities"], extracted
        facts = {entity["field"]: entity["value"] for entity in extracted["entities"]}
        assert facts["甲方"] == "甲方示例科技有限公司", facts
        assert facts["乙方"] == "乙方示例服务有限公司", facts
        assert facts["付款期限"] == "三十日", facts
        assert extracted["sources"], extracted
        print("PASS cited deterministic entity extraction", flush=True)

        summary = await call_chat(
            client, "总结合同付款条款和违约责任", doc_id
        )
        assert summary["tools_called"] == ["summarize_document"], summary
        assert summary["status"] == "answered", summary
        assert summary["sources"], summary
        assert "[" in summary["answer"] and "]" in summary["answer"]
        assert "检索片段" in summary["answer"]
        print("PASS evidence-scoped live Qwen summary", flush=True)

        combined = await call_chat(
            client, "提取甲乙方并总结合同付款和违约责任", doc_id
        )
        assert combined["status"] == "answered", combined
        assert set(combined["tools_called"]) == {
            "extract_entities", "summarize_document"
        }, combined
        assert combined["plan_source"] in (
            "llm_validated", "rule_fallback"
        ), combined
        assert combined["steps"] == 2, combined
        assert len(combined["sources"]) >= 3, combined
        print("PASS multi-tool LangGraph plan + unique citations", flush=True)

    print("M3b PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
