"""M4b: real PostgreSQL + Qdrant long-term memory, across two sessions.

Uses caller-supplied demo UUIDs (not authentication). Only a whitelisted
explicit document-analysis format preference may be written.
"""

import asyncio
from uuid import uuid4

import asyncpg
import httpx

from app.core.config import get_settings
from app.memory.long_term import LongTermMemory


CONTRACT = (
    "合同主体：甲方为示例科技有限公司，乙方为示例服务有限公司。"
    "乙方提供软件开发服务，经甲方验收后，甲方应于三十日内付款。"
    "甲方逾期付款需按合同约定承担违约责任。"
)
PREFERENCE = "请记住：以后合同分析按“主体、金额、期限、风险、引用”格式输出。"


async def main() -> None:
    settings = get_settings()
    user_a, user_b = str(uuid4()), str(uuid4())
    print("DEMO_USER_ID:", user_a, flush=True)
    async with httpx.AsyncClient(
        base_url="http://127.0.0.1:8000", timeout=600, trust_env=False
    ) as client:
        up = await client.post(
            "/v1/documents",
            files={"file": ("m4b_preference.txt", CONTRACT.encode("utf-8"), "text/plain")},
        )
        up.raise_for_status()
        doc_id = up.json()["document_id"]
        indexing = await client.post(f"/v1/documents/{doc_id}/index")
        indexing.raise_for_status()
        print("Indexed document:", doc_id, flush=True)

        saved_response = await client.post(
            "/v1/chat",
            json={"query": PREFERENCE, "user_id": user_a},
        )
        saved_response.raise_for_status()
        saved = saved_response.json()
        assert saved["status"] == "memory_saved", saved
        memory_id = saved["memory_saved"]["memory_id"]
        assert saved["memory_saved"]["content"] == (
            "合同分析输出格式：主体、金额、期限、风险、引用"
        )
        print("PASS explicit preference save:", memory_id, flush=True)

        # Confirm DB persistence independently of the memory API.
        pg = await asyncpg.connect(settings.postgres_dsn)
        try:
            row = await pg.fetchrow(
                "SELECT id, user_id, content, is_indexed FROM memories WHERE id=$1",
                uuid4() if not memory_id else __import__("uuid").UUID(memory_id),
            )
            assert row and str(row["user_id"]) == user_a and row["is_indexed"], row
        finally:
            await pg.close()
        print("PASS PostgreSQL structured memory", flush=True)

        # Brand-new session: user_id remains stable, session_id is new.
        query = "根据这份合同，总结主体、付款期限及违约风险。"
        recalled = await client.post(
            "/v1/chat",
            json={"query": query, "document_id": doc_id, "user_id": user_a},
        )
        if recalled.status_code != 200:
            print("Recall API error:", recalled.status_code, recalled.text[:800], flush=True)
        recalled.raise_for_status()
        answer = recalled.json()
        print(
            "Cross-session result:", answer["status"], answer["answer"], flush=True
        )
        assert answer["session_id"] != saved["session_id"], answer
        assert answer["memory_applied"] is True, answer
        assert any(m["memory_id"] == memory_id for m in answer["retrieved_memories"])
        assert answer["status"] == "answered", answer
        assert answer["sources"], answer
        print("PASS cross-session semantic preference recall", flush=True)

        # Idempotent retry must reuse the existing PostgreSQL row.
        again = await client.post(
            "/v1/chat",
            json={"query": PREFERENCE, "user_id": user_a},
        )
        again.raise_for_status()
        assert again.json()["memory_saved"]["memory_id"] == memory_id

    memory = LongTermMemory()
    different_user = await memory.search(
        __import__("uuid").UUID(user_b), "合同分析主体金额期限风险引用"
    )
    assert different_user == [], different_user

    pg = await asyncpg.connect(settings.postgres_dsn)
    try:
        count = await pg.fetchval(
            "SELECT COUNT(*) FROM memories WHERE user_id=$1",
            __import__("uuid").UUID(user_a),
        )
        assert count == 1, count
    finally:
        await pg.close()
    print("PASS idempotent upsert and user-isolated semantic recall", flush=True)
    print("M4b MEMORY PASS", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
