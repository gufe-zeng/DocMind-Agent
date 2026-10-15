"""M6b PostgreSQL approval store with exact-once note persistence.

Lifecycle:
  PENDING (no write) -> APPROVED (decision) -> review_notes insert by graph
  PENDING (no write) -> REJECTED (never insert)

Approval decisions are persisted before graph resume. The resumed,
approval-gated graph inserts the actual note and binds review_note_id
atomically. Multiple resumes/replayed requests cannot create duplicates.
"""

from pathlib import Path
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

import asyncpg

from app.core.config import get_settings


class ApprovalConflict(ValueError):
    """Incompatible decision or identity for an existing approval."""


def _dsn() -> str:
    return get_settings().postgres_dsn


def _public(row: dict) -> dict:
    return {
        "approval_id": str(row["id"]),
        "session_id": str(row["session_id"]),
        "user_id": str(row["user_id"]),
        "document_id": str(row["document_id"]),
        "tool": row["tool_name"],
        "status": row["status"],
        "review_note_id": str(row["review_note_id"]) if row["review_note_id"] else None,
    }


async def init_approval_schema(dsn: str) -> None:
    sql = (
        Path(__file__).resolve().parents[2]
        / "migrations" / "003_approvals.sql"
    ).read_text(encoding="utf-8")
    conn = await asyncpg.connect(dsn=dsn, timeout=10)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def create_approval(
    *, session_id: UUID, user_id: UUID, document_id: UUID, note: str
) -> dict:
    if not (1 <= len(note) <= 500) or "\x00" in note:
        raise ValueError("Invalid review note.")
    approval_id = uuid4()
    conn = await asyncpg.connect(dsn=_dsn(), timeout=10)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO approvals
                (id, session_id, user_id, document_id, tool_name, note_text)
            SELECT $1, $2, $3, d.id, 'save_review_note', $5
              FROM documents AS d WHERE d.id=$4 AND d.status='indexed'
            RETURNING id, session_id, user_id, document_id,
                      tool_name, status, review_note_id
            """,
            approval_id, session_id, user_id, document_id, note,
        )
    finally:
        await conn.close()
    if row is None:
        raise ValueError("Only an indexed, existing document can be reviewed.")
    return _public(dict(row))


async def get_approval(approval_id: UUID) -> dict | None:
    conn = await asyncpg.connect(dsn=_dsn(), timeout=10)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, session_id, user_id, document_id, tool_name,
                   status, review_note_id, note_text
              FROM approvals WHERE id=$1
            """,
            approval_id,
        )
    finally:
        await conn.close()
    return dict(row) if row else None


async def decide_approval(
    approval_id: UUID, *,
    session_id: UUID, user_id: UUID, decision: str
) -> dict:
    """Persist an authenticated-*demo-scope* decision without writing the note."""
    if decision not in ("approve", "reject"):
        raise ValueError("Invalid approval decision.")
    requested_status = "approved" if decision == "approve" else "rejected"
    conn = await asyncpg.connect(dsn=_dsn(), timeout=10)
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM approvals WHERE id=$1 FOR UPDATE", approval_id
            )
            if row is None:
                raise LookupError("Approval not found.")
            if row["session_id"] != session_id or row["user_id"] != user_id:
                raise ApprovalConflict("Approval session/user scope mismatch.")
            if row["status"] not in ("pending", requested_status):
                raise ApprovalConflict("Approval was already decided differently.")
            if row["status"] == "pending":
                row = await conn.fetchrow(
                    """
                    UPDATE approvals
                       SET status=$2, decided_at=NOW()
                     WHERE id=$1
                     RETURNING *
                    """,
                    approval_id, requested_status,
                )
            return _public(dict(row))
    finally:
        await conn.close()


async def execute_approved_review_note(approval_id: UUID, *,
                                       session_id: UUID, user_id: UUID) -> dict:
    """Exactly-once protected write; invoked only after LangGraph interrupt."""
    note_id = uuid5(NAMESPACE_URL, f"docmind:review-note:{approval_id}")
    conn = await asyncpg.connect(dsn=_dsn(), timeout=10)
    try:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM approvals WHERE id=$1 FOR UPDATE", approval_id
            )
            if row is None:
                raise LookupError("Approval not found.")
            if row["session_id"] != session_id or row["user_id"] != user_id:
                raise ApprovalConflict("Approval session/user scope mismatch.")
            if row["status"] != "approved":
                raise ApprovalConflict("Write requires a persisted approve decision.")
            if row["review_note_id"] is None:
                await conn.execute(
                    """
                    INSERT INTO review_notes
                        (id, approval_id, document_id, session_id, user_id, content)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (approval_id) DO NOTHING
                    """,
                    note_id, approval_id, row["document_id"],
                    session_id, user_id, row["note_text"],
                )
                # Also works if an earlier attempt committed the unique
                # note but the graph itself did not checkpoint its result.
                saved_id = await conn.fetchval(
                    "SELECT id FROM review_notes WHERE approval_id=$1",
                    approval_id,
                )
                if saved_id is None:
                    raise RuntimeError("Approved note write failed.")
                await conn.execute(
                    "UPDATE approvals SET review_note_id=$2 WHERE id=$1",
                    approval_id, saved_id,
                )
            else:
                saved_id = row["review_note_id"]
            return {
                "approval_id": str(approval_id),
                "review_note_id": str(saved_id),
                "status": "approved",
                "document_id": str(row["document_id"]),
            }
    finally:
        await conn.close()
