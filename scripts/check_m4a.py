"""M4a live Docker gate: two-turn Redis memory + PostgreSQL checkpoints.

Checks previously established M3 business tools and a new short follow-up
without re-uploading/re-specifying document_id. This is a real model run,
not a deterministic LLM stub.

The output prints SESSION_ID for optional validation across API restarts.
"""

import asyncio
from uuid import uuid4

import httpx
from redis.asyncio import Redis

from app.core.config import get_settings
from app.memory.checkpoint import open_checkpointer, thread_config


CONTRACT = (
    "甲方：甲方示例科技有限公司。\n"
    "乙方：乙方示例服务有限公司。\n"
    "付款条款：乙方完成服务并经甲方验收合格后，甲方应在三十日内支付款项。\n"
    "违约责任：若甲方逾期付款，应按照合同约定承担违约责任，"
    "每日按逾期未支付金额的千分之一支付违约金。"
)


async def _answer(client, payload):
    r = await client.post("/v1/chat", json=payload)
    if r.status_code != 200:
        print("Chat HTTP error:", r.status_code, r.text[:1000], flush=True)
    r.raise_for_status()
    data = r.json()
    print(
        f"question={payload['query']}\n"
        f"status={data['status']} context_applied={data['context_applied']}\n"
        f"answer={data['answer']}",
        flush=True,
    )
    return data


async def main() -> None:
    settings = get_settings()
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000",
        timeout=600,
        trust_env=False,
    ) as client:
        up = await client.post(
            "/v1/documents",
            files={"file": ("m4a_payment.txt", CONTRACT.encode(), "text/plain")},
        )
        up.raise_for_status()
        document_id = up.json()["document_id"]
        indexing = await client.post(f"/v1/documents/{document_id}/index")
        indexing.raise_for_status()
        print("Indexed document:", document_id, flush=True)

        first = await _answer(
            client,
            {
                "query": "根据合同，验收合格后付款期限是多少天？",
                "document_id": document_id,
            },
        )
        assert first["status"] == "answered", first
        assert "[S1]" in first["answer"]
        assert first["context_applied"] is False
        sid = first["session_id"]
        print("SESSION_ID=" + sid, flush=True)

        second = await _answer(
            client,
            {"query": "如果逾期呢？", "session_id": sid},
        )
        assert second["session_id"] == sid
        assert second["context_applied"] is True
        assert second["effective_document_id"] == document_id
        assert second["status"] == "answered", second
        assert "[S1]" in second["answer"], second
        assert second["sources"], second
        assert all(source["document_id"] == document_id for source in second["sources"])
        print("PASS same-session document resolution and follow-up expansion", flush=True)

        saved = await client.get(f"/v1/sessions/{sid}")
        saved.raise_for_status()
        snapshot = saved.json()
        assert snapshot["document_id"] == document_id
        assert snapshot["turn_count"] == 2
        assert snapshot["checkpoint_saved"] is True
        assert snapshot["turns"][0]["query"].startswith("根据合同")
        assert snapshot["turns"][1]["query"] == "如果逾期呢？"
        assert "上一问题" in snapshot["turns"][1]["resolved_query"]
        print("PASS Redis persisted two bounded session turns", flush=True)

        absent = await client.get(f"/v1/sessions/{uuid4()}")
        assert absent.status_code == 404, absent.text

    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        remaining = await redis.ttl("docmind:session:" + sid)
        assert 0 < remaining <= settings.session_ttl_seconds, remaining
        print("PASS Redis session TTL:", remaining, flush=True)
    finally:
        await redis.aclose()

    # A separate PostgreSQL connection loads the snapshot that the API
    # saved. This proves the checkpoint is not merely an in-process cache.
    async with open_checkpointer(settings.postgres_dsn) as independent:
        tup = await independent.aget_tuple(thread_config(sid))
        assert tup is not None and tup.checkpoint is not None
        values = tup.checkpoint.get("channel_values") or {}
        assert values.get("session_id") == sid, values
        assert values.get("final_answer"), values
        assert values.get("current_step", 0) >= 1, values
        print("PASS independent PostgreSQL checkpoint load", flush=True)

    print("M4a PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
