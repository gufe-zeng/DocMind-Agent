"""M6b local Docker end-to-end Human Approval test, including API restart.

Two phases are run by scripts/check_m6b.bat:
  prepare: create pending approval via POST /v1/chat, verify no write
  (Windows Docker Compose restarts API, PostgreSQL/Redis remain intact)
  finish: resume the actual checkpoint via POST /v1/approvals/{id},
          assert single transactional note, replay idempotency and reject path

No Qwen is required. Only explicitly provided synthetic review-note text is
saved. Test uses the real FastAPI, LangGraph and PostgreSQL services.
"""

import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

import asyncpg
import httpx

from app.agent.graph import build_agent_graph
from app.core.config import get_settings
from app.memory.checkpoint import open_checkpointer, thread_config


STATE_PATH = Path("/app/data/uploads/.m6b_acceptance.json")
DOCUMENT = (
    "合同付款期限：乙方交付并验收合格后，甲方三十日内付款。\n"
    "违约责任：逾期付款应按合同约定处理。"
)
REVIEW_NOTE = "请人工复核验收与付款条款的衔接。"
REJECTED_NOTE = "待进一步讨论的内部审查意见。"


async def wait_ready(client: httpx.AsyncClient) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + 90
    while True:
        try:
            response = await client.get("/health", timeout=5)
            response.raise_for_status()
            if response.json()["status"] != "ok":
                raise ValueError("DocMind dependencies not ready.")
            return
        except (httpx.HTTPError, ValueError) as exc:
            if loop.time() >= deadline:
                raise RuntimeError("DocMind API did not become ready.") from exc
            await asyncio.sleep(2)


async def db_approval(approval_id: str) -> tuple[dict, list[dict]]:
    settings = get_settings()
    pg = await asyncpg.connect(dsn=settings.postgres_dsn, timeout=10)
    try:
        row = await pg.fetchrow(
            "SELECT * FROM approvals WHERE id=$1", UUID(approval_id)
        )
        rows = await pg.fetch(
            "SELECT * FROM review_notes WHERE approval_id=$1",
            UUID(approval_id),
        )
        assert row is not None
        return dict(row), [dict(item) for item in rows]
    finally:
        await pg.close()


async def check_checkpoint(session_id: str, approval_id: str, *, paused: bool) -> None:
    settings = get_settings()
    async with open_checkpointer(settings.postgres_dsn) as saver:
        graph = build_agent_graph(checkpointer=saver)
        snapshot = await graph.aget_state(thread_config(session_id))
        assert snapshot and snapshot.values["approval_id"] == approval_id, snapshot
        if paused:
            assert "call_tool" in snapshot.next, snapshot.next
            assert snapshot.values["current_step"] == 0
            assert snapshot.values["next_tool"] == "save_review_note"
        else:
            assert not snapshot.next, snapshot.next
            assert snapshot.values["current_step"] == 1


async def call_json(client: httpx.AsyncClient, route: str, payload: dict,
                    *, expect: int = 200) -> dict:
    response = await client.post(route, json=payload)
    if response.status_code != expect:
        print(
            "API mismatch:", route, response.status_code,
            response.text[:1200], flush=True,
        )
    assert response.status_code == expect, response.text
    return response.json()


async def prepare() -> None:
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False,
    ) as http:
        await wait_ready(http)
        up = await http.post(
            "/v1/documents",
            files={"file": ("m6b_review.txt", DOCUMENT.encode(), "text/plain")},
        )
        up.raise_for_status()
        document_id = up.json()["document_id"]
        indexing = await http.post(f"/v1/documents/{document_id}/index")
        indexing.raise_for_status()
        assert indexing.json()["status"] == "indexed"

        user_id = str(uuid4())
        pending = await call_json(
            http, "/v1/chat",
            {
                "query": "请保存审核备注：" + REVIEW_NOTE,
                "document_id": document_id,
                "user_id": user_id,
            },
        )
        assert pending["status"] == "approval_required", pending
        assert pending["approval_required"] is True
        assert pending["approval_id"]
        assert pending["tools_called"] == []
        assert pending["steps"] == 0
        approval_id = pending["approval_id"]
        session_id = pending["session_id"]
        print(
            "PENDING_APPROVAL_ID=" + approval_id,
            "SESSION_ID=" + session_id, flush=True,
        )

        row, notes = await db_approval(approval_id)
        assert row["status"] == "pending" and row["review_note_id"] is None
        assert row["note_text"] == REVIEW_NOTE
        assert notes == [], notes
        print("PASS pending approval persisted and no pre-approval write", flush=True)

        await check_checkpoint(session_id, approval_id, paused=True)
        print("PASS LangGraph interrupted before save_review_note", flush=True)

        # Explicit local-demo scope checks must fail before any decision.
        wrong = {
            "decision": "approve", "session_id": session_id,
            "user_id": str(uuid4()),
        }
        await call_json(
            http, f"/v1/approvals/{approval_id}", wrong, expect=403
        )
        await call_json(
            http, f"/v1/approvals/{approval_id}",
            {
                "decision": "approve", "session_id": str(uuid4()),
                "user_id": user_id,
            },
            expect=403,
        )
        await call_json(
            http, "/v1/chat",
            {
                "query": "请列出已上传文档",
                "session_id": session_id,
                "user_id": user_id,
            },
            expect=409,
        )
        row, notes = await db_approval(approval_id)
        assert row["status"] == "pending" and notes == []
        print("PASS mismatched scope denied and paused thread protected", flush=True)

    STATE_PATH.write_text(
        json.dumps({
            "approval_id": approval_id,
            "session_id": session_id,
            "user_id": user_id,
            "document_id": document_id,
        }),
        encoding="utf-8",
    )
    print("M6b PREPARE PASS — restart API and resume the checkpoint", flush=True)


async def finish() -> None:
    test = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    approval_id = test["approval_id"]
    session_id = test["session_id"]
    user_id = test["user_id"]
    document_id = test["document_id"]

    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False,
    ) as http:
        await wait_ready(http)
        row, notes = await db_approval(approval_id)
        assert row["status"] == "pending" and notes == []
        await check_checkpoint(session_id, approval_id, paused=True)
        print("PASS approval + paused graph survive API container restart", flush=True)

        approve = {
            "decision": "approve",
            "session_id": session_id,
            "user_id": user_id,
        }
        authorized = await call_json(
            http, f"/v1/approvals/{approval_id}", approve
        )
        assert authorized["status"] == "approved"
        assert authorized["checkpoint_completed"] is True
        note_id = authorized["review_note_id"]
        assert note_id
        row, notes = await db_approval(approval_id)
        assert row["status"] == "approved"
        assert str(row["review_note_id"]) == note_id
        assert len(notes) == 1 and notes[0]["content"] == REVIEW_NOTE, notes
        assert str(notes[0]["document_id"]) == document_id
        await check_checkpoint(session_id, approval_id, paused=False)
        print("PASS approved note saved once after LangGraph resume", flush=True)

        repeated = await call_json(
            http, f"/v1/approvals/{approval_id}", approve
        )
        assert repeated["review_note_id"] == note_id
        assert repeated["status"] == "approved"
        await call_json(
            http, f"/v1/approvals/{approval_id}",
            {**approve, "decision": "reject"},
            expect=409,
        )
        _, notes = await db_approval(approval_id)
        assert len(notes) == 1
        print("PASS approval replay idempotent; conflicting decision rejected", flush=True)

        # A separate approval request must be rejected without any write.
        waiting = await call_json(
            http, "/v1/chat",
            {
                "query": "保存审查备注：" + REJECTED_NOTE,
                "document_id": document_id,
                "user_id": user_id,
            },
        )
        assert waiting["status"] == "approval_required", waiting
        reject_id = waiting["approval_id"]
        reject_sid = waiting["session_id"]
        row, notes = await db_approval(reject_id)
        assert row["status"] == "pending" and notes == []

        rejection = {
            "decision": "reject",
            "session_id": reject_sid,
            "user_id": user_id,
        }
        rejected = await call_json(
            http, f"/v1/approvals/{reject_id}", rejection
        )
        assert rejected["status"] == "rejected"
        assert rejected["review_note_id"] is None
        assert rejected["checkpoint_completed"] is True
        row, notes = await db_approval(reject_id)
        assert row["status"] == "rejected" and notes == []
        await check_checkpoint(reject_sid, reject_id, paused=False)

        repeat_reject = await call_json(
            http, f"/v1/approvals/{reject_id}", rejection
        )
        assert repeat_reject["status"] == "rejected"
        await call_json(
            http, f"/v1/approvals/{reject_id}",
            {**rejection, "decision": "approve"},
            expect=409,
        )
        _, notes = await db_approval(reject_id)
        assert notes == []
        print("PASS reject/replay never writes and later approval blocked", flush=True)

        await call_json(
            http, "/v1/chat",
            {
                "query": "保存审核备注：",
                "user_id": user_id,
                "document_id": document_id,
            },
            expect=422,
        )
        print("PASS malformed write request rejected before creating approval", flush=True)

    STATE_PATH.unlink(missing_ok=True)
    print("M6b HITL PASS", flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "finish"):
        raise SystemExit("Usage: python scripts/check_m6b.py prepare|finish")
    asyncio.run(prepare() if sys.argv[1] == "prepare" else finish())
