"""M7c live Docker system profiling. No new HTTP endpoint or server instrumentation.

Default mode measures real serial Agent HTTP calls, M6 tool-event latencies,
and standalone BGE hybrid-retrieval/rerank stages WITHOUT Qwen.

--live also executes a separate real RAG/Qwen probe and counts its actual
completion calls + usage. No result is fabricated when usage is unavailable.
"""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter

import httpx

from app.core.config import get_settings
from app.rag.retriever import hybrid_search
from app.rag.reranker import rerank_hits
from eval.system_eval import AgentTiming, LiveLLMProbe, evaluate_system


CONTRACT = (
    "甲方：M7C测试采购有限公司。\n"
    "乙方：M7C测试服务有限公司。\n"
    "付款条款：服务验收合格后，甲方在三十日内支付款项。\n"
    "违约责任：如果甲方逾期付款，应当按合同约定支付违约金。"
)
STAGE_QUERY = "服务验收后三十日内付款及逾期违约金"
AGENT_CASES = (
    ("metadata", "查询文档信息", ("query_document_metadata",), ()),
    ("mcp_clause", "通过MCP查找违约责任条款", ("mcp_find_clause",), ("find_clause",)),
    ("mcp_search", "通过MCP检索逾期付款违约金", ("mcp_search_documents",),
     ("search_documents",)),
    ("mcp_multi", "通过MCP查询文档信息并查找违约责任条款",
     ("mcp_get_document", "mcp_find_clause"), ("get_document", "find_clause")),
)


async def wait_ready(http: httpx.AsyncClient) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 90
    while True:
        try:
            response = await http.get("/health", timeout=5)
            response.raise_for_status()
            if response.json().get("status") != "ok":
                raise RuntimeError("API is not healthy")
            print("PASS M7c API ready", flush=True)
            return
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            if loop.time() >= deadline:
                raise RuntimeError("M7c API not available") from exc
            await asyncio.sleep(2)


async def index_fixture(http: httpx.AsyncClient) -> str:
    upload = await http.post(
        "/v1/documents",
        files={"file": ("m7c_latency.txt", CONTRACT.encode("utf-8"), "text/plain")},
    )
    upload.raise_for_status()
    document_id = upload.json()["document_id"]
    indexed = await http.post(f"/v1/documents/{document_id}/index")
    indexed.raise_for_status()
    if indexed.json().get("status") != "indexed":
        raise RuntimeError("Synthetic document was not indexed")
    print(f"Indexed M7c fixture: {document_id}", flush=True)
    return document_id


async def profile_agent(http: httpx.AsyncClient, document_id: str) -> list[AgentTiming]:
    samples: list[AgentTiming] = []
    for case_id, query, expected, mcp_expected in AGENT_CASES:
        started = perf_counter()
        try:
            response = await http.post(
                "/v1/chat", json={"query": query, "document_id": document_id},
            )
            elapsed = (perf_counter() - started) * 1000
            payload = response.json() if response.status_code == 200 else {}
            if not isinstance(payload, dict):
                payload = {}
            tools = tuple(payload.get("tools_called", ()))
            events = tuple(payload.get("tool_events", ()))
            mcp_tools = tuple(payload.get("mcp_tools_called", ()))
            status = payload.get("status")
            valid_no_llm_path = (
                response.status_code == 200
                and payload.get("plan_source") == "rules"
                and tools == expected
                and mcp_tools == mcp_expected
                and payload.get("steps") == len(expected)
                and status == "answered"
            )
            sources = payload.get("sources") or []
            correct_scope = (
                isinstance(sources, list)
                and all(
                    isinstance(s, dict) and s.get("document_id") == document_id
                    for s in sources
                )
            )
            valid_no_llm_path = valid_no_llm_path and correct_scope
            print(
                f"CASE {case_id}: status={status} steps={payload.get('steps')} "
                f"latency_ms={elapsed:.2f} tool_events={len(events)}",
                flush=True,
            )
            samples.append(AgentTiming(
                case_id=case_id, latency_ms=elapsed,
                http_status=response.status_code, agent_status=status,
                tools_called=tools, tool_events=events,
                verified_no_llm=valid_no_llm_path,
            ))
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            elapsed = (perf_counter() - started) * 1000
            print(f"CASE {case_id}: {type(exc).__name__}", flush=True)
            samples.append(AgentTiming(
                case_id=case_id, latency_ms=elapsed,
                http_status=None, agent_status=None, tools_called=(),
                tool_events=(), verified_no_llm=False,
            ))
    return samples


async def profile_stages(document_id: str) -> tuple[float, float]:
    settings = get_settings()
    started = perf_counter()
    candidates = await hybrid_search(
        STAGE_QUERY, document_id=document_id,
        top_k=settings.rag_candidate_k,
        candidate_k=max(settings.rag_candidate_k, 20),
    )
    retrieval_ms = (perf_counter() - started) * 1000
    if not candidates or any(hit.document_id != document_id for hit in candidates):
        raise AssertionError("Scoped live retrieval returned invalid evidence")
    started = perf_counter()
    reranked = await asyncio.to_thread(
        rerank_hits, STAGE_QUERY, candidates,
        model_name=settings.reranker_model,
        cache_dir=settings.embedding_cache_dir,
        limit=settings.rag_evidence_k,
    )
    rerank_ms = (perf_counter() - started) * 1000
    if not reranked:
        raise AssertionError("BGE reranker returned no results")
    print(
        f"PASS standalone Dense/BM25/RRF retrieval {retrieval_ms:.2f}ms "
        f"and BGE rerank {rerank_ms:.2f}ms",
        flush=True,
    )
    return retrieval_ms, rerank_ms


async def profile_live_qwen(document_id: str) -> LiveLLMProbe:
    """Wrap only the evaluator's in-process RAG LLM call, not the API server."""
    from app.rag import pipeline

    original_completion = pipeline.complete_chat
    calls = 0

    async def counted_completion(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original_completion(*args, **kwargs)

    pipeline.complete_chat = counted_completion
    started = perf_counter()
    try:
        response = await pipeline.answer_document_question(
            "服务验收合格后，甲方应在多少日内付款？", document_id=document_id,
        )
    finally:
        pipeline.complete_chat = original_completion
    elapsed = (perf_counter() - started) * 1000
    print(
        f"LIVE RAG: status={response.status} calls={calls} "
        f"prompt_tokens={response.prompt_tokens} "
        f"completion_tokens={response.completion_tokens} "
        f"elapsed_ms={elapsed:.2f}",
        flush=True,
    )
    if calls != 1 or response.status != "answered" or not response.citation_valid:
        raise AssertionError("Live Qwen RAG must answer with verified citations in one call")
    return LiveLLMProbe(
        latency_ms=elapsed, calls=calls, status=response.status,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
    )


async def main(live: bool) -> None:
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False,
    ) as http:
        await wait_ready(http)
        document_id = await index_fixture(http)
        agent_samples = await profile_agent(http, document_id)

    retrieval_ms, rerank_ms = await profile_stages(document_id)
    live_probe = await profile_live_qwen(document_id) if live else None
    report = evaluate_system(
        agent_samples, standalone_retrieval_ms=retrieval_ms,
        standalone_rerank_ms=rerank_ms, live_llm_probe=live_probe,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)

    assert report["agent_http_answered"] == len(AGENT_CASES)
    assert report["agent_failure_count"] == 0
    assert report["read_only_tool_calls"] == 5
    assert report["tool_event_coverage"] == 1.0
    assert report["agent_e2e_latency"]["samples"] == len(AGENT_CASES)
    assert report["tool_latency"]["samples"] == 5
    assert report["standalone_retrieval_latency_ms"] is not None
    assert report["standalone_rerank_latency_ms"] is not None
    assert report["llm_usage"]["agent_request_llm_calls"] == 0, (
        "Rule/MCP-only API workload unexpectedly entered an unverified route"
    )
    if live:
        usage = report["llm_usage"]["live_rag_probe"]
        assert usage and usage["llm_calls"] == 1
        assert usage["tokens_measured"], (
            "LLM provider did not return token usage: cannot validate M7c live token metrics"
        )
        print("M7c SYSTEM LIVE PASS", flush=True)
    else:
        print("M7c SYSTEM BASE PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Also call real Qwen RAG")
    args = parser.parse_args()
    asyncio.run(main(args.live))
