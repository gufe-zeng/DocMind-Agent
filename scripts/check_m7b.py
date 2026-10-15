"""M7b Docker smoke: evaluate the real Agent API against a fixed task fixture.

Only rule-selected tools, deterministic extraction, and actual MCP transport
are exercised. Qwen is intentionally unnecessary for this smoke benchmark.
"""
import asyncio
import json
from pathlib import Path

import fitz
import httpx

from eval.agent_eval import AgentEvalCase, evaluate_agent


FIXTURE = Path(__file__).resolve().parents[1] / "eval" / "datasets" / "m7b_agent.json"


def pdf_bytes(pages: list[str]) -> bytes:
    document = fitz.open()
    try:
        for text in pages:
            page = document.new_page()
            page.insert_text((72, 72), text)
        return document.tobytes()
    finally:
        document.close()


def file_bytes(item: dict) -> bytes:
    if item["type"] == "text/plain":
        return item["text"].encode("utf-8")
    if item["type"] == "application/pdf":
        return pdf_bytes(item["pages"])
    raise ValueError(f"Unsupported fixture document type: {item['type']}")


async def wait_ready(http: httpx.AsyncClient) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 90
    while True:
        try:
            response = await http.get("/health", timeout=5)
            response.raise_for_status()
            if response.json().get("status") != "ok":
                raise RuntimeError("API dependencies not ready")
            print("PASS M7b API ready", flush=True)
            return
        except (httpx.HTTPError, RuntimeError, ValueError) as exc:
            if loop.time() >= deadline:
                raise RuntimeError("API not ready before M7b evaluation") from exc
            await asyncio.sleep(2)


async def upload_and_index(http: httpx.AsyncClient, item: dict) -> str:
    up = await http.post(
        "/v1/documents",
        files={"file": (item["filename"], file_bytes(item), item["type"])},
    )
    up.raise_for_status()
    doc_id = up.json()["document_id"]
    index = await http.post(f"/v1/documents/{doc_id}/index")
    index.raise_for_status()
    if index.json().get("status") != "indexed":
        raise RuntimeError(f"Fixture not indexed: {item['key']}")
    print(f"Indexed {item['key']}: {doc_id}", flush=True)
    return doc_id


def case_from_json(item: dict, ids: dict[str, str]) -> AgentEvalCase:
    return AgentEvalCase(
        case_id=item["id"],
        expected_tools=tuple(item["expected_tools"]),
        expected_status=item.get("expected_status", "answered"),
        expected_mcp_tools=tuple(item.get("expected_mcp_tools", [])),
        answer_contains=tuple(item.get("answer_contains", [])),
        expected_entities=tuple(sorted(item.get("expected_entities", {}).items())),
        expected_document_id=ids[item["doc"]],
        expected_page=item.get("expected_page"),
        require_sources=item.get("require_sources", False),
    )


async def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["version"] == 1, "Unknown M7b fixture version"
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False,
    ) as http:
        await wait_ready(http)
        doc_ids = {}
        for doc in fixture["documents"]:
            doc_ids[doc["key"]] = await upload_and_index(http, doc)

        cases = [case_from_json(item, doc_ids) for item in fixture["cases"]]
        responses: list[dict | None] = []
        for item in fixture["cases"]:
            try:
                reply = await http.post("/v1/chat", json={
                    "query": item["query"],
                    "document_id": doc_ids[item["doc"]],
                })
                if reply.status_code != 200:
                    print(
                        f"CASE {item['id']}: HTTP {reply.status_code} "
                        f"{reply.text[:400]}",
                        flush=True,
                    )
                    responses.append(None)
                    continue
                payload = reply.json()
                if not isinstance(payload, dict):
                    raise ValueError("Agent response is not a JSON object")
                responses.append(payload)
                print(
                    f"CASE {item['id']}: status={payload.get('status')} "
                    f"tools={payload.get('tools_called')} "
                    f"steps={payload.get('steps')}",
                    flush=True,
                )
            except (httpx.HTTPError, ValueError) as exc:
                print(
                    f"CASE {item['id']}: request failure ({type(exc).__name__})",
                    flush=True,
                )
                responses.append(None)

    metrics = evaluate_agent(cases, responses)
    metrics["dataset_version"] = fixture["version"]
    print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)
    assert all(
        (
            metrics["task_success_rate"] == 1.0,
            metrics["tool_selection_accuracy"] == 1.0,
            metrics["mcp_tool_selection_accuracy"] == 1.0,
            metrics["tool_success_rate"] == 1.0,
            metrics["failure_rate"] == 0.0,
        )
    ), "M7b Agent fixture failed: inspect per-case results above."
    print("M7b AGENT EVAL PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
