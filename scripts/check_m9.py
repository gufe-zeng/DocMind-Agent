"""M9: deterministic local DocMind-Agent V1 business demo over frozen public APIs.

BASE: synthetic TXT/PDF/DOCX -> indexing -> Agent/MCP/extraction ->
      Redis multi-turn -> long-term preference -> HITL approve/replay ->
      PostgreSQL trace and Prometheus sanity.
LIVE: one real Qwen RAG answer on the indexed synthetic contract.
No new API or extra network model download is needed in BASE.
"""
import argparse
import asyncio
import io
import json
import re
from pathlib import Path
from uuid import UUID, uuid4

import asyncpg
import fitz
import httpx
from docx import Document

from app.core.config import get_settings


BASE_URL = "http://127.0.0.1:8000"
STATE_FILE = Path("/app/data/uploads/.m9_demo_state.json")
REPORT_FILE = Path("/app/data/uploads/.m9_demo_report.json")
CONTRACT_TXT = (
    "甲方：蓝海技术有限公司\n"
    "乙方：启航服务有限公司\n"
    "付款期限：甲方应在服务验收合格后三十日内支付合同价款。\n"
    "违约责任：如甲方逾期付款，应依合同约定承担违约责任并支付违约金。\n"
    "保密条款：双方应对技术资料保密。\n"
)
PDF_PAGES = (
    "DOCMIND M9 SAMPLE CONTRACT, PAGE 1",
    "DOCMIND M9 SECOND PAGE DELIVERY TERMS",
)
DOCX_TEXT = (
    "示例服务合同",
    "甲方：星河采购有限公司",
    "乙方：远航交付有限公司",
    "违约责任：迟延交付应按约定承担违约责任和违约金。",
)
_CITATION_RE = re.compile(r"\[(S\d+)\]")


def make_pdf(pages: tuple[str, ...] = PDF_PAGES) -> bytes:
    doc = fitz.open()
    try:
        for paragraph in pages:
            page = doc.new_page()
            page.insert_text((72, 72), paragraph)
        return doc.tobytes()
    finally:
        doc.close()


def make_docx(lines: tuple[str, ...] = DOCX_TEXT) -> bytes:
    doc = Document()
    for line in lines:
        doc.add_paragraph(line)
    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()


def fixture_files() -> tuple[tuple[str, bytes, str], ...]:
    return (
        ("m9_contract.txt", CONTRACT_TXT.encode("utf-8"), "text/plain"),
        ("m9_pages.pdf", make_pdf(), "application/pdf"),
        ("m9_contract.docx", make_docx(),
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    )


def assert_citations(
    reply: dict, document_id: str, *, required_page: int | None = None
) -> None:
    """Reject fabricated citation IDs, missing chunk provenance and scope leaks."""
    answer = reply.get("answer")
    sources = reply.get("sources")
    assert isinstance(answer, str) and isinstance(sources, list) and sources
    cited = set(_CITATION_RE.findall(answer))
    ids = [source.get("id") for source in sources]
    assert cited and len(set(ids)) == len(ids)
    assert cited.issubset(set(ids))
    for source in sources:
        assert source.get("document_id") == document_id
        assert source.get("chunk_id") and source.get("filename")
        assert isinstance(source.get("evidence"), str) and source["evidence"]
        if required_page is not None:
            assert source.get("page") == required_page


def summarize_result(name: str, reply: dict) -> dict:
    """Summary intentionally excludes raw response text and evidence."""
    return {
        "stage": name,
        "status": reply["status"],
        "tools_called": reply.get("tools_called", []),
        "mcp_tools_called": reply.get("mcp_tools_called", []),
        "source_count": len(reply.get("sources", [])),
        "trace_id": reply.get("trace_id"),
    }


def live_failure_diagnostic(reply: dict, llm_calls: int | None) -> dict:
    """Return only bounded tool control-plane data, never Qwen/contract text."""
    fields = (
        "tool", "status", "attempts", "retries", "timeout_seconds",
        "duration_ms", "error_type",
    )
    return {
        "status": reply.get("status"),
        "trace_id": reply.get("trace_id"),
        "tools_called": reply.get("tools_called", []),
        "tool_events": [
            {field: event[field] for field in fields if field in event}
            for event in reply.get("tool_events", [])
            if isinstance(event, dict)
        ],
        "llm_calls": llm_calls,
    }


async def wait_healthy(http: httpx.AsyncClient) -> None:
    loop = asyncio.get_running_loop()
    until = loop.time() + 90
    while True:
        try:
            response = await http.get("/health", timeout=5)
            response.raise_for_status()
            if response.json().get("status") != "ok":
                raise RuntimeError("Unhealthy DocMind dependencies")
            print("PASS DocMind API /health and dependencies ready", flush=True)
            return
        except (httpx.HTTPError, ValueError, RuntimeError) as exc:
            if loop.time() >= until:
                raise RuntimeError("M9 API health timeout") from exc
            await asyncio.sleep(2)


async def post_json(http: httpx.AsyncClient, path: str, payload: dict) -> dict:
    response = await http.post(path, json=payload)
    if response.status_code != 200:
        print(f"M9 HTTP {response.status_code} at {path}: {response.text[:450]}", flush=True)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("API response was not a JSON object")
    return body


async def index_demo_file(
    http: httpx.AsyncClient, filename: str, content: bytes, content_type: str
) -> str:
    uploaded = await http.post(
        "/v1/documents", files={"file": (filename, content, content_type)}
    )
    uploaded.raise_for_status()
    doc_id = uploaded.json()["document_id"]
    index = await http.post(f"/v1/documents/{doc_id}/index")
    index.raise_for_status()
    assert index.json().get("status") == "indexed", index.json()
    return str(UUID(doc_id))


async def database_scalar(query: str, *params) -> object:
    conn = await asyncpg.connect(dsn=get_settings().postgres_dsn, timeout=10)
    try:
        return await conn.fetchval(query, *params)
    finally:
        await conn.close()


async def assert_trace(reply: dict, *, expect_llm: bool = False) -> None:
    trace = reply.get("trace_id")
    request = reply.get("request_id")
    session = reply.get("session_id")
    assert all(isinstance(s, str) for s in (trace, request, session))
    conn = await asyncpg.connect(dsn=get_settings().postgres_dsn, timeout=10)
    try:
        row = await conn.fetchrow(
            """SELECT request_id, session_id, status, llm_calls,
                      prompt_tokens, completion_tokens,
                      node_events, tool_names
               FROM agent_traces WHERE trace_id = $1""",
            UUID(trace),
        )
    finally:
        await conn.close()
    assert row is not None, "M9 request lacks persisted M8 trace"
    assert row["request_id"] == UUID(request)
    assert row["session_id"] == UUID(session)
    assert row["status"] == reply["status"]
    assert row["llm_calls"] >= 1 if expect_llm else row["llm_calls"] == 0
    assert row["node_events"], "Missing LangGraph node spans"
    names = row["tool_names"]
    if isinstance(names, str):
        names = json.loads(names)
    assert names == reply.get("tools_called", [])


def validate_demo_state(state: dict) -> None:
    assert state.get("schema_version") == 1
    doc_ids = state.get("documents")
    assert isinstance(doc_ids, dict) and set(doc_ids) == {"txt", "pdf", "docx"}
    for value in doc_ids.values():
        UUID(value)
    UUID(state["user_id"])
    assert isinstance(state.get("case_results"), list)


async def run_base() -> None:
    result_rows: list[dict] = []
    user_id = str(uuid4())
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=600, trust_env=False
    ) as http:
        await wait_healthy(http)
        # Sequential indexing avoids a first-run Qdrant collection/model-cache race.
        indexed_ids = []
        for filename, payload, content_type in fixture_files():
            indexed_ids.append(await index_demo_file(
                http, filename, payload, content_type
            ))
        txt, pdf, docx = indexed_ids
        docs = {"txt": txt, "pdf": pdf, "docx": docx}
        print("PASS TXT/PDF/DOCX uploaded and indexed with real services", flush=True)

        multi = await post_json(http, "/v1/chat", {
            "query": "通过MCP查询文档信息并查找违约责任条款",
            "document_id": txt,
        })
        assert multi["status"] == "answered"
        assert multi["tools_called"] == ["mcp_get_document", "mcp_find_clause"]
        assert multi["mcp_tools_called"] == ["get_document", "find_clause"]
        assert_citations(multi, txt)
        assert "违约责任" in multi["answer"]
        await assert_trace(multi)
        result_rows.append(summarize_result("multi_tool_mcp", multi))
        print("PASS LangGraph -> MCP two-tool chain with scoped citations", flush=True)

        extraction = await post_json(http, "/v1/chat", {
            "query": "提取甲乙方及付款期限", "document_id": txt,
        })
        assert extraction["status"] == "answered"
        assert extraction["tools_called"] == ["extract_entities"]
        assert_citations(extraction, txt)
        values = {row["field"]: row["value"] for row in extraction["entities"]}
        for field, expected in {
            "甲方": "蓝海技术有限公司",
            "乙方": "启航服务有限公司",
            "付款期限": "三十日",
        }.items():
            assert values.get(field) == expected, values
        await assert_trace(extraction)
        result_rows.append(summarize_result("deterministic_extraction", extraction))
        print("PASS source-grounded party/payment extraction with citations", flush=True)

        page = await post_json(http, "/v1/chat", {
            "query": "通过MCP读取第2页的内容", "document_id": pdf,
        })
        assert page["status"] == "answered"
        assert page["mcp_tools_called"] == ["get_document_page"]
        assert "SECOND PAGE DELIVERY TERMS" in page["answer"]
        assert_citations(page, pdf, required_page=2)
        await assert_trace(page)
        result_rows.append(summarize_result("pdf_page_provenance", page))
        print("PASS actual PDF page-2 source provenance", flush=True)

        docx_answer = await post_json(http, "/v1/chat", {
            "query": "通过MCP查找违约责任条款", "document_id": docx,
        })
        assert docx_answer["status"] == "answered"
        assert "违约责任" in docx_answer["answer"]
        assert_citations(docx_answer, docx)
        await assert_trace(docx_answer)
        result_rows.append(summarize_result("docx_clause", docx_answer))
        print("PASS parsed DOCX clause retrieval and citation", flush=True)

        first_turn = await post_json(http, "/v1/chat", {
            "query": "通过MCP查找违约责任条款", "document_id": txt,
            "user_id": user_id,
        })
        assert first_turn["status"] == "answered"
        followup = await post_json(http, "/v1/chat", {
            "query": "如果逾期，通过MCP查找违约责任条款",
            "session_id": first_turn["session_id"], "user_id": user_id,
        })
        assert followup["status"] == "answered"
        assert followup["context_applied"] is True
        assert followup["effective_document_id"] == txt
        assert_citations(followup, txt)
        sessions = await http.get(f"/v1/sessions/{first_turn['session_id']}")
        sessions.raise_for_status()
        assert sessions.json()["turn_count"] >= 2
        assert sessions.json()["checkpoint_saved"] is True
        await assert_trace(followup)
        result_rows.append(summarize_result("redis_multiturn", followup))
        print("PASS Redis session follow-up and PostgreSQL checkpoint", flush=True)

        saved = await post_json(http, "/v1/chat", {
            "query": "请记住合同分析输出格式：主体、金额、期限、风险、引用",
            "document_id": txt, "user_id": user_id,
        })
        assert saved["status"] == "memory_saved"
        assert saved["memory_saved"]["content"].startswith("合同分析输出格式：")
        another = await post_json(http, "/v1/chat", {
            "query": "通过MCP查找合同违约责任条款",
            "document_id": txt, "user_id": user_id,
        })
        assert another["status"] == "answered"
        assert any(m["key"] == "contract_analysis_format"
                   for m in another.get("retrieved_memories", [])), another
        assert_citations(another, txt)
        await assert_trace(another)
        result_rows.append(summarize_result("cross_session_preference", another))
        print("PASS explicit preference persisted and recalled in new session", flush=True)

        pending = await post_json(http, "/v1/chat", {
            "query": "保存审核备注：请人工复核付款期限和违约金条款。",
            "document_id": txt, "user_id": user_id,
        })
        assert pending["status"] == "approval_required"
        assert pending["approval_required"] and pending["approval_id"]
        approval_id = UUID(pending["approval_id"])
        before = await database_scalar(
            "SELECT COUNT(*) FROM review_notes WHERE approval_id=$1", approval_id
        )
        assert before == 0, "Protected note written before approval"
        await assert_trace(pending)
        approved = await post_json(
            http, f"/v1/approvals/{approval_id}", {
                "decision": "approve",
                "session_id": pending["session_id"], "user_id": user_id,
            },
        )
        assert approved["status"] == "approved" and approved["review_note_id"]
        written = await database_scalar(
            "SELECT COUNT(*) FROM review_notes WHERE approval_id=$1", approval_id
        )
        assert written == 1
        replay = await post_json(
            http, f"/v1/approvals/{approval_id}", {
                "decision": "approve",
                "session_id": pending["session_id"], "user_id": user_id,
            },
        )
        assert replay["review_note_id"] == approved["review_note_id"]
        assert await database_scalar(
            "SELECT COUNT(*) FROM review_notes WHERE approval_id=$1", approval_id
        ) == 1
        conflicting = await http.post(
            f"/v1/approvals/{approval_id}",
            json={
                "decision": "reject", "session_id": pending["session_id"],
                "user_id": user_id,
            },
        )
        assert conflicting.status_code == 409
        await assert_trace(approved)
        result_rows.append(summarize_result("hitl_approval", approved))
        print("PASS HITL guarded write, approved once, replay idempotent, conflict denied",
              flush=True)

        stats = await http.get("/metrics")
        stats.raise_for_status()
        for required in (
            "agent_requests_total", "agent_e2e_latency_seconds_count",
            "tool_calls_total", "tool_latency_seconds_count",
        ):
            assert required in stats.text
        print("PASS Prometheus /metrics and persisted request-level Agent traces",
              flush=True)

    state = {
        "schema_version": 1, "documents": docs, "user_id": user_id,
        "case_results": result_rows,
        "live_qwen": None,
    }
    validate_demo_state(state)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    REPORT_FILE.write_text(json.dumps({
        "scope": "synthetic demo, local Docker, frozen V1 API",
        "base_case_count": len(result_rows),
        "case_results": result_rows,
        "live_qwen": None,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "document_ids": docs,
        "base_case_count": len(result_rows),
        "trace_ids": [row["trace_id"] for row in result_rows],
        "report_in_container": str(REPORT_FILE),
    }, ensure_ascii=False, indent=2), flush=True)
    print("M9 DEMO BASE PASS", flush=True)


async def run_live() -> None:
    assert STATE_FILE.exists(), "Run M9 base before optional LIVE mode."
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    validate_demo_state(state)
    document_id = state["documents"]["txt"]
    from app.core.config import get_settings
    configured_timeout = get_settings().rag_cpu_timeout_seconds
    async with httpx.AsyncClient(
        base_url=BASE_URL, timeout=max(600.0, configured_timeout + 60),
        trust_env=False,
    ) as http:
        await wait_healthy(http)
        answer = await post_json(http, "/v1/chat", {
            "query": "这份合同的付款期限是多少？",
            "document_id": document_id,
        })
        if answer.get("status") != "answered":
            # When CPU ONNX/Qwen fails, surface persisted, sanitized evidence
            # immediately rather than a bare AssertionError after minutes.
            attempts = await database_scalar(
                "SELECT llm_calls FROM agent_traces WHERE trace_id=$1",
                UUID(answer["trace_id"]),
            )
            details = live_failure_diagnostic(answer, attempts)
            print("M9 LIVE FAILURE DIAGNOSTICS: "
                  + json.dumps(details, ensure_ascii=False, indent=2),
                  flush=True)
            raise AssertionError(
                f"M9 LIVE RAG failed with status={answer.get('status')}; "
                "see tool_events/error_type and llm_calls above."
            )
        assert answer["tools_called"] == ["search_documents"]
        events = answer.get("tool_events", [])
        assert len(events) == 1
        assert events[0].get("status") == "ok"
        assert events[0].get("attempts") == 1
        assert events[0].get("timeout_seconds") == configured_timeout
        assert ("三十" in answer["answer"] or "30" in answer["answer"])
        assert_citations(answer, document_id)
        await assert_trace(answer, expect_llm=True)
        print("PASS real Qwen hybrid-RAG answer with factual deadline/citation",
              flush=True)
        metrics = await http.get("/metrics")
        metrics.raise_for_status()
        assert "llm_calls_total" in metrics.text
        print("PASS Qwen request and token observations in Agent telemetry",
              flush=True)

    brief = summarize_result("qwen_grounded_rag", answer)
    state["live_qwen"] = brief
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                          encoding="utf-8")
    result = json.loads(REPORT_FILE.read_text(encoding="utf-8"))
    result["live_qwen"] = brief
    REPORT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(json.dumps(brief, ensure_ascii=False, indent=2), flush=True)
    print("M9 DEMO LIVE PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("base", "live"))
    args = parser.parse_args()
    asyncio.run(run_base() if args.mode == "base" else run_live())
