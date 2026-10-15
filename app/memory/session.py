"""M4a Redis session memory: bounded turns, TTL, document context, and lock.

Only short recent user/assistant turns are stored. Qdrant source chunks and
raw tool traces are intentionally excluded from this session memory.
Long-term user preferences are a separate M4b responsibility.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import secrets
from typing import Any
from uuid import UUID

from redis.asyncio import Redis


class SessionBusyError(RuntimeError):
    """Another request is running against this session ID."""


def _session_id(value: str) -> str:
    return str(UUID(value))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(
        self, redis: Redis, *, ttl_seconds: int = 3600,
        max_turns: int = 6, lock_seconds: int = 300,
    ):
        if ttl_seconds <= 0 or not (1 <= max_turns <= 20) or lock_seconds <= 0:
            raise ValueError("Invalid session store TTL, history or lock bounds.")
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self.max_turns = max_turns
        self.lock_seconds = lock_seconds

    def _key(self, session_id: str) -> str:
        return "docmind:session:" + _session_id(session_id)

    @asynccontextmanager
    async def lock(self, session_id: str):
        """Prevent overlapping turns for the same session (time-limited lease)."""
        key = self._key(session_id) + ":lock"
        token = secrets.token_hex(16)
        acquired = await self.redis.set(
            key, token, ex=self.lock_seconds, nx=True
        )
        if not acquired:
            raise SessionBusyError("Session has a running request.")
        try:
            yield
        finally:
            # Atomic compare/delete: never remove a later request's lock.
            await self.redis.eval(
                "if redis.call('GET', KEYS[1]) == ARGV[1] then "
                "return redis.call('DEL', KEYS[1]) else return 0 end",
                1, key, token,
            )

    async def read(self, session_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self._key(session_id))
        if raw is None:
            return None
        session = json.loads(raw)
        if not isinstance(session, dict) or session.get("session_id") != _session_id(session_id):
            raise RuntimeError("Invalid session memory payload.")
        return session

    async def append_turn(
        self, session_id: str, *, document_id: str | None,
        query: str, resolved_query: str, answer: str, status: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Called once after successful graph execution, while lock is held."""
        session_id = _session_id(session_id)
        document_id = str(UUID(document_id)) if document_id else None
        existing = await self.read(session_id)
        if user_id is not None:
            user_id = str(UUID(user_id))
        previous_user = existing.get("user_id") if existing else None
        if previous_user and user_id and previous_user != user_id:
            raise ValueError("Session user_id cannot change.")
        user_id = previous_user or user_id
        now = _now()
        session = existing or {
            "session_id": session_id,
            "created_at": now,
            "turns": [],
        }
        session["document_id"] = document_id
        if user_id is not None:
            session["user_id"] = user_id
        session["updated_at"] = now
        session["turns"] = [
            *(session.get("turns", [])[-self.max_turns + 1:] if self.max_turns > 1 else []),
            {
                "query": query[:1000],
                "resolved_query": resolved_query[:1000],
                "answer": answer[:1200],
                "status": status,
                "timestamp": now,
            },
        ]
        encoded = json.dumps(session, ensure_ascii=False)
        await self.redis.set(self._key(session_id), encoded, ex=self.ttl_seconds)
        return session


FOLLOWUP_MARKERS = (
    "如果", "逾期", "那", "它", "这个", "这些", "这种", "上述",
    "还有", "继续", "之前", "上一", "如果没有", "对方", "然后",
)


def resolve_followup(
    query: str,
    previous: dict[str, Any] | None,
    *,
    document_id: str | None,
) -> tuple[str, bool]:
    """Conservative, transparent context expansion for short follow-ups.

    No model call, no invented facts: only prior user question and the new
    question are used. The same-document requirement prevents unrelated
    sessions/documents being mixed.
    """
    if not previous or not previous.get("turns") or len(query) > 60:
        return query, False
    previous_document = previous.get("document_id")
    if document_id is None or previous_document != document_id:
        return query, False
    if not any(marker in query for marker in FOLLOWUP_MARKERS):
        return query, False

    last_question = str(previous["turns"][-1].get("query", ""))[:160].strip()
    if not last_question:
        return query, False
    return (
        f"同一文档中的上一问题：{last_question}。"
        f"当前追问：{query}。请根据文档证据解释追问涉及的条款。",
        True,
    )
