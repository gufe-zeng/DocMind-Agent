"""M6b unit checks: unapproved writes never run and LangGraph truly pauses."""

from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent.graph import build_agent_graph
from app.agent.router import select_tool_plan
from app.approvals.policy import is_review_note_command, parse_review_note
from app.memory.checkpoint import thread_config
from app.tools.registry import invoke_tool


def test_explicit_write_intent_is_bounded_and_no_llm_planner_can_invent_it():
    text = "请保存审核备注：请人工复核付款条件。"
    assert is_review_note_command(text)
    assert select_tool_plan(text) == ["save_review_note"]
    assert parse_review_note(text) == "请人工复核付款条件。"
    assert not is_review_note_command("请分析合同付款条件")
    assert select_tool_plan("请分析合同付款条件") == ["search_documents"]

    with pytest.raises(ValueError):
        parse_review_note("保存审核备注：")
    with pytest.raises(ValueError):
        parse_review_note("保存审核备注：" + "字" * 501)
    with pytest.raises(ValueError):
        select_tool_plan("保存审核备注：")


@pytest.mark.asyncio
async def test_protected_tool_cannot_use_normal_read_only_registry():
    with pytest.raises(ValueError, match="not registered"):
        await invoke_tool(
            "save_review_note",
            arguments={"document_id": str(uuid4()), "note": "bypass"},
        )


@pytest.mark.asyncio
async def test_langgraph_interrupts_before_approved_note_write(monkeypatch):
    from app.approvals import storage

    session_id, user_id, document_id, approval_id = [
        str(uuid4()) for _ in range(4)
    ]
    calls = []

    async def fake_get(identifier):
        assert identifier == UUID(approval_id)
        return {
            "id": identifier, "session_id": UUID(session_id),
            "user_id": UUID(user_id), "document_id": UUID(document_id),
            "status": "approved", "review_note_id": None,
        }

    async def fake_write(identifier, *, session_id, user_id):
        calls.append(identifier)
        return {"review_note_id": str(uuid4()), "status": "approved"}

    monkeypatch.setattr(storage, "get_approval", fake_get)
    monkeypatch.setattr(storage, "execute_approved_review_note", fake_write)

    graph = build_agent_graph(checkpointer=InMemorySaver())
    cfg = thread_config(session_id)
    first = await graph.ainvoke({
        "query": "保存审核备注：付款条款需进一步审核。",
        "session_id": session_id,
        "user_id": user_id,
        "document_id": document_id,
        "approval_id": approval_id,
    }, config=cfg)
    assert first.get("__interrupt__"), first
    snapshot = await graph.aget_state(cfg)
    assert "call_tool" in snapshot.next
    assert snapshot.values["approval_id"] == approval_id
    assert snapshot.values["current_step"] == 0
    assert not calls, "Protected writes must never execute before approval"

    result = await graph.ainvoke(
        Command(resume={"approval_id": approval_id, "decision": "approve"}),
        config=cfg,
    )
    assert result["status"] == "approved", result
    assert result["tools_called"] == ["save_review_note"]
    assert result["current_step"] == 1
    assert len(calls) == 1
    assert not (await graph.aget_state(cfg)).next


@pytest.mark.asyncio
async def test_rejected_approval_resumes_without_any_note_write(monkeypatch):
    from app.approvals import storage

    session_id, user_id, document_id, approval_id = [
        str(uuid4()) for _ in range(4)
    ]

    async def rejected(identifier):
        return {
            "session_id": UUID(session_id),
            "user_id": UUID(user_id),
            "document_id": UUID(document_id),
            "status": "rejected",
        }

    async def forbidden(*args, **kwargs):
        raise AssertionError("Rejected notes must never be inserted")

    monkeypatch.setattr(storage, "get_approval", rejected)
    monkeypatch.setattr(storage, "execute_approved_review_note", forbidden)

    graph = build_agent_graph(checkpointer=InMemorySaver())
    cfg = thread_config(session_id)
    await graph.ainvoke({
        "query": "保存审核备注：请复核发票金额。",
        "session_id": session_id, "user_id": user_id,
        "document_id": document_id, "approval_id": approval_id,
    }, config=cfg)
    result = await graph.ainvoke(
        Command(resume={"approval_id": approval_id, "decision": "reject"}),
        config=cfg,
    )
    assert result["status"] == "rejected", result
    assert result["sources"] == []
    assert result["current_step"] == 1
    assert "未执行写入" in result["final_answer"]
