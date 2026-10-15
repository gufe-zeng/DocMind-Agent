"""M4a: Redis short-term state, history-aware query expansion and checkpoint turns.

All unit tests are offline and use a fake Redis adapter plus LangGraph's
ephemeral InMemorySaver for state-reset semantics. End-to-end runs use real
Redis/PostgreSQL through scripts/check_m4a.py.
"""

import asyncio
import json
from uuid import uuid4

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import build_agent_graph
from app.api.chat import _initial_state
from app.memory.checkpoint import thread_config
from app.memory.session import SessionBusyError, SessionStore, resolve_followup


class FakeRedis:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, *, ex=None, nx=False):
        if nx and key in self.data:
            return None
        self.data[key] = value
        if ex is not None:
            self.ttls[key] = ex
        return True

    async def eval(self, script, numkeys, key, token):
        assert numkeys == 1
        if self.data.get(key) == token:
            del self.data[key]
            return 1
        return 0


@pytest.mark.asyncio
async def test_redis_memory_bounded_by_turns_and_ttl():
    backend = FakeRedis()
    store = SessionStore(backend, ttl_seconds=180, max_turns=3)
    sid = str(uuid4())
    document = str(uuid4())

    async with store.lock(sid):
        for index in range(5):
            await store.append_turn(
                sid, document_id=document, query=f"q{index}",
                resolved_query=f"q{index}", answer=f"a{index}",
                status="answered",
            )
    session = await store.read(sid)
    assert session["document_id"] == document
    assert [turn["query"] for turn in session["turns"]] == ["q2", "q3", "q4"]
    assert backend.ttls[store._key(sid)] == 180


@pytest.mark.asyncio
async def test_lock_prevents_same_session_overlap_and_releases_safely():
    store = SessionStore(FakeRedis(), ttl_seconds=60)
    sid = str(uuid4())
    async with store.lock(sid):
        with pytest.raises(SessionBusyError):
            async with store.lock(sid):
                raise AssertionError("Should not acquire an already held lock")
    async with store.lock(sid):
        pass


def test_followup_uses_only_same_document_history():
    document = str(uuid4())
    old = {
        "document_id": document,
        "turns": [{"query": "合同验收后付款期限是什么？", "answer": "三十日"}],
    }
    expanded, applied = resolve_followup(
        "如果逾期呢？", old, document_id=document
    )
    assert applied and "合同验收后付款期限" in expanded
    assert "如果逾期呢" in expanded

    original, applied = resolve_followup(
        "如果逾期呢？", old, document_id=str(uuid4())
    )
    assert not applied and original == "如果逾期呢？"
    original, applied = resolve_followup(
        "合同违约责任是什么？", old, document_id=document
    )
    assert not applied and original == "合同违约责任是什么？"


@pytest.mark.asyncio
async def test_checkpointed_thread_resets_transient_state_each_turn(monkeypatch):
    async def fixed_planner(query, document_id=None):
        from app.agent.router import PlanDecision
        return PlanDecision(["query_document_metadata"], "rules")

    async def fake_tool(name, *, arguments):
        return {
            "tool": "query_document_metadata",
            "status": "answered",
            "documents": [{
                "filename": "contract.txt",
                "status": "indexed",
                "chunk_count": 1,
            }],
        }

    monkeypatch.setattr("app.agent.nodes.plan_tools", fixed_planner)
    monkeypatch.setattr("app.agent.nodes.invoke_tool", fake_tool)

    graph = build_agent_graph(checkpointer=InMemorySaver())
    sid = str(uuid4())
    config = thread_config(sid)
    doc_id = str(uuid4())

    first = await graph.ainvoke(
        _initial_state(sid, query="列出文档", document_id=doc_id),
        config=config,
    )
    assert first["current_step"] == 1

    second = await graph.ainvoke(
        _initial_state(sid, query="还有文档吗？", document_id=doc_id),
        config=config,
    )
    assert second["current_step"] == 1, "Do not accumulate prior turn steps"
    assert second["tools_called"] == ["query_document_metadata"]
    snapshot = await graph.aget_state(config)
    assert snapshot.values["final_answer"] == second["final_answer"]
    assert snapshot.values["session_id"] == sid


def test_session_id_validation():
    with pytest.raises(ValueError):
        SessionStore(FakeRedis())._key("../other-user")
