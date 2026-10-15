"""M6b approval decision API: resume the persisted LangGraph HITL checkpoint.

POST /v1/approvals/{approval_id} is the frozen V1 endpoint.
The request must identify the exact local-demo session and user UUID.
These UUIDs are NOT authentication; local access is required.
"""

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from app.approvals.storage import (
    ApprovalConflict,
    decide_approval,
    get_approval,
)
from app.memory.checkpoint import thread_config
from app.memory.session import SessionBusyError


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["approvals"])


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    session_id: UUID
    user_id: UUID


class ApprovalDecisionResponse(BaseModel):
    approval_id: UUID
    session_id: UUID
    status: Literal["approved", "rejected"]
    review_note_id: UUID | None = None
    checkpoint_completed: bool
    answer: str


def _approved_response(row: dict, *, completed: bool) -> ApprovalDecisionResponse:
    status = row["status"]
    if status not in ("approved", "rejected"):
        raise RuntimeError("Cannot acknowledge a pending approval.")
    if status == "approved" and row["review_note_id"] is None:
        raise RuntimeError("Cannot acknowledge approval without a saved note.")
    return ApprovalDecisionResponse(
        approval_id=row["id"],
        session_id=row["session_id"],
        status=status,
        review_note_id=row["review_note_id"],
        checkpoint_completed=completed,
        answer=(
            "审核备注已获批准并保存。" if status == "approved"
            else "审核备注已被拒绝，未执行写入。"
        ),
    )


@router.post(
    "/approvals/{approval_id}",
    response_model=ApprovalDecisionResponse,
)
async def decide_review_note(
    approval_id: UUID,
    body: ApprovalDecisionRequest,
    http_request: Request,
) -> ApprovalDecisionResponse:
    store = http_request.app.state.session_store
    graph = http_request.app.state.agent_graph
    cfg = thread_config(str(body.session_id))

    try:
        async with store.lock(str(body.session_id)):
            row = await get_approval(approval_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Approval not found.")
            if row["session_id"] != body.session_id or row["user_id"] != body.user_id:
                raise HTTPException(status_code=403, detail="Approval scope mismatch.")

            snapshot = await graph.aget_state(cfg)
            waiting = (
                snapshot is not None
                and "call_tool" in snapshot.next
                and snapshot.values.get("next_tool") == "save_review_note"
                and snapshot.values.get("approval_id") == str(approval_id)
            )
            decided_status = (
                "approved" if body.decision == "approve" else "rejected"
            )

            # Idempotent request after a prior completed graph invocation:
            # return the persisted result and NEVER execute the write twice.
            if row["status"] == decided_status and not snapshot.next:
                return _approved_response(row, completed=True)
            if row["status"] not in ("pending", decided_status):
                raise HTTPException(
                    status_code=409, detail="Approval already decided differently."
                )
            if not waiting:
                raise HTTPException(
                    status_code=409,
                    detail="Matching paused LangGraph write checkpoint not found.",
                )

            # Persist decision first. A crash after this statement leaves
            # the paused checkpoint available for safe, idempotent replay.
            await decide_approval(
                approval_id, session_id=body.session_id,
                user_id=body.user_id, decision=body.decision,
            )
            resumed = await graph.ainvoke(
                Command(resume={
                    "approval_id": str(approval_id),
                    "decision": body.decision,
                }),
                config=cfg,
            )
            if resumed.get("status") != decided_status:
                raise RuntimeError("Graph did not complete the approval decision.")
            after = await get_approval(approval_id)
            if after is None:
                raise RuntimeError("Approval row disappeared after graph resume.")
            verified = _approved_response(after, completed=True)

            # Redis is bounded recent history, not the write source of truth.
            # If this update fails, resubmission reads the committed DB
            # decision and the completed graph checkpoint.
            await store.append_turn(
                str(body.session_id),
                document_id=str(row["document_id"]),
                user_id=str(body.user_id),
                query="审核备注审批：" + body.decision,
                resolved_query="审核备注审批：" + body.decision,
                answer=verified.answer,
                status=decided_status,
            )
            return verified

    except HTTPException:
        raise
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Approval decision failed: approval_id=%s", approval_id)
        raise HTTPException(
            status_code=503,
            detail="Approval/checkpoint service unavailable. Inspect API logs.",
        ) from exc
