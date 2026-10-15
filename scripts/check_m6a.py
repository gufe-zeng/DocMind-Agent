"""M6a real Docker gate: live MCP + bounded, injected tool failures.

Synthetic fault injection runs in this validation process only; no test-only
HTTP endpoints or fault switches are added to the production FastAPI server.
The real MCP call checks backward compatibility with the accepted M5 chain.
"""

import asyncio

import httpx

from app.agent.graph import build_agent_graph
from app.agent import nodes
from app.agent.router import PlanDecision
from app.agent.reliability import ToolPolicy, execute_read_only_tool


CONTRACT = (
    "合同付款期限：验收合格后三十日内付款。\n"
    "违约责任：若甲方逾期付款，需按合同约定承担违约金。"
)


async def wait_for_api(client: httpx.AsyncClient) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + 90
    while True:
        try:
            r = await client.get("/health", timeout=5)
            r.raise_for_status()
            assert r.json()["status"] == "ok"
            print("PASS DocMind API ready", flush=True)
            return
        except (httpx.HTTPError, ValueError, AssertionError) as exc:
            if loop.time() > end:
                raise RuntimeError("API unavailable before M6a smoke test.") from exc
            await asyncio.sleep(2)


async def main() -> None:
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600,
        trust_env=False,
    ) as http:
        await wait_for_api(http)
        upload = await http.post(
            "/v1/documents",
            files={"file": ("m6a_retry.txt", CONTRACT.encode("utf-8"), "text/plain")},
        )
        upload.raise_for_status()
        doc_id = upload.json()["document_id"]
        indexed = await http.post(f"/v1/documents/{doc_id}/index")
        indexed.raise_for_status()
        assert indexed.json()["status"] == "indexed"
        print("Indexed:", doc_id, flush=True)

        # Existing MCP /v1/chat contract still works with runtime metadata.
        answer = await http.post(
            "/v1/chat",
            json={"query": "通过MCP查找违约责任条款", "document_id": doc_id},
        )
        answer.raise_for_status()
        actual = answer.json()
        assert actual["status"] == "answered", actual
        assert actual["mcp_tools_called"] == ["find_clause"], actual
        assert actual["retry_count"] == 0, actual
        assert actual["tool_events"][0]["status"] == "ok", actual
        assert all(s["document_id"] == doc_id for s in actual["sources"])
        assert "[S1]" in actual["answer"]
        print("PASS real Agent -> MCP tool with success trace", flush=True)

    original_tool, original_plan = nodes.invoke_tool, nodes.plan_tools
    try:
        attempts = 0

        async def flaky_metadata(name, *, arguments):
            nonlocal attempts
            attempts += 1
            if attempts <= 2:
                raise httpx.ConnectError("M6a synthetic transient outage")
            return await original_tool(name, arguments=arguments)

        nodes.invoke_tool = flaky_metadata
        result = await build_agent_graph().ainvoke(
            {"query": "列出已上传的文档", "document_id": None}
        )
        assert result["status"] == "answered", result
        assert attempts == 3, attempts
        assert result["retry_count"] == 2, result
        assert result["current_step"] == 1, result
        assert result["reliability_events"][0]["attempts"] == 3, result
        assert "m6a_retry.txt" in result["final_answer"]
        print("PASS two retries recover real PostgreSQL metadata read", flush=True)

        async def all_down(name, *, arguments):
            if name == "query_document_metadata":
                raise httpx.ConnectError("M6a injected outage")
            return await original_tool(name, arguments=arguments)

        nodes.invoke_tool = all_down
        down = await build_agent_graph().ainvoke(
            {"query": "列出已上传的文档", "document_id": None}
        )
        assert down["status"] == "tool_unavailable", down
        assert down["retry_count"] == 2 and down["sources"] == [], down
        assert "未找到已上传" not in down["final_answer"], down
        print("PASS exhausted retries return fail-closed no-facts fallback", flush=True)

        async def combined_plan(query, document_id=None):
            return PlanDecision(
                tools=["query_document_metadata", "mcp_find_clause"],
                source="rules",
            )

        nodes.plan_tools = combined_plan
        mixed = await build_agent_graph().ainvoke(
            {"query": "通过MCP查找违约责任条款", "document_id": doc_id}
        )
        assert mixed["status"] == "partial", mixed
        assert mixed["tools_called"] == [
            "query_document_metadata", "mcp_find_clause"
        ], mixed
        assert mixed["retry_count"] == 2 and mixed["current_step"] == 2, mixed
        assert mixed["sources"] and all(
            s["document_id"] == doc_id for s in mixed["sources"]
        ), mixed
        assert "[S1]" in mixed["final_answer"], mixed
        print("PASS partial multi-tool result keeps real MCP citations", flush=True)

        calls = 0

        async def too_slow(name, *, arguments):
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.5)
            return {"tool": name, "status": "answered"}

        timeout_result = await execute_read_only_tool(
            "query_document_metadata", arguments={}, executor=too_slow,
            policy=ToolPolicy(timeout_seconds=0.01, backoff_seconds=0),
        )
        assert calls == 3
        assert timeout_result.result["status"] == "tool_unavailable"
        assert timeout_result.event["error_type"] == "TimeoutError"
        print("PASS bounded tool timeout and 2 retry limit", flush=True)
    finally:
        nodes.invoke_tool, nodes.plan_tools = original_tool, original_plan

    print("M6a PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
