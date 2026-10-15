"""M4a /v1/chat: Redis-backed recent sessions + PostgreSQL graph checkpoints.

Session identifiers are local-dev bearer tokens, not authenticated identities.
They must not be exposed as a multi-user service without access control.
"""

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.agent.state import AgentState
from app.memory.checkpoint import thread_config
from app.memory.long_term import format_hint, is_memory_command, parse_format_preference
from app.memory.session import SessionBusyError, resolve_followup


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1", tags=["agent"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    document_id: UUID | None = None
    session_id: UUID | None = None
    user_id: UUID | None = None


class ChatResponse(BaseModel):
    request_id: UUID
    session_id: UUID
    status: str
    intent: str
    answer: str
    tools_called: list[str]
    plan_source: str
    planner_fallback_reason: str | None = None
    steps: int
    entities: list[dict]
    sources: list[dict]
    context_applied: bool = False
    effective_document_id: UUID | None = None
    memory_saved: dict | None = None
    retrieved_memories: list[dict] = Field(default_factory=list)
    memory_applied: bool = False


class SessionResponse(BaseModel):
    session_id: UUID
    document_id: UUID | None = None
    created_at: str
    updated_at: str
    turn_count: int
    turns: list[dict]
    checkpoint_saved: bool


def _initial_state(
    session_id: str, *, query: str, document_id: str | None,
    format_hint: str | None = None,
) -> AgentState:
    """Reset turn-local state while keeping the persistent graph thread."""
    return {
        "session_id": session_id,
        "query": query,
        "document_id": document_id,
        "format_hint": format_hint,
        "messages": [],
        "intent": "",
        "plan": [],
        "plan_source": "",
        "planner_fallback_reason": None,
        "next_tool": None,
        "retrieved_docs": [],
        "tool_results": [],
        "entities": [],
        "current_step": 0,
        "retry_count": 0,
        "approval_required": False,
        "final_answer": "",
        "status": "starting",
        "sources": [],
        "tools_called": [],
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, http_request: Request) -> ChatResponse:
    session_id = request.session_id or uuid4()
    request_id = uuid4()
    sid = str(session_id)
    store = http_request.app.state.session_store
    graph = http_request.app.state.agent_graph
    memory = http_request.app.state.long_term_memory

    try:
        async with store.lock(sid):
            previous = await store.read(sid)
            previous_user = previous.get("user_id") if previous else None
            supplied_user = str(request.user_id) if request.user_id else None
            if previous_user and supplied_user and previous_user != supplied_user:
                raise HTTPException(status_code=409, detail="Session identity mismatch.")
            user_id = UUID(supplied_user or previous_user) if (supplied_user or previous_user) else None
            requested_doc = str(request.document_id) if request.document_id else None
            document_id = (
                requested_doc if requested_doc is not None
                else (previous.get("document_id") if previous else None)
            )
            resolved_query, used_context = resolve_followup(
                request.query, previous, document_id=document_id
            )
            result: AgentState = await graph.ainvoke(
                _initial_state(sid, query=resolved_query, document_id=document_id),
                config=thread_config(sid),
            )
            answer = result.get("final_answer", "")
            status = result.get("status", "unknown")

            # Store only accepted/reported answer text and bounded recent
            # dialogue; do not save raw retrieved excerpts in Redis.
            await store.append_turn(
                sid,
                document_id=document_id,
                query=request.query,
                resolved_query=resolved_query,
                answer=answer,
                status=status,
            )

            return ChatResponse(
                request_id=request_id,
                session_id=session_id,
                status=status,
                intent=result.get("intent", "unknown"),
                answer=answer,
                tools_called=result.get("tools_called", []),
                plan_source=result.get("plan_source", "rules"),
                planner_fallback_reason=result.get("planner_fallback_reason"),
                steps=result.get("current_step", 0),
                entities=result.get("entities", []),
                sources=result.get("sources", []),
                context_applied=used_context,
                effective_document_id=UUID(document_id) if document_id else None,
            )
    except SessionBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Agent execution failed: request_id=%s", request_id)
        raise HTTPException(
            status_code=503,
            detail="Agent or session/checkpoint service unavailable. Inspect API logs.",
        ) from exc


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: UUID, http_request: Request) -> SessionResponse:
    store = http_request.app.state.session_store
    graph = http_request.app.state.agent_graph
    try:
        session = await store.read(str(session_id))
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found or expired.")
        snapshot = await graph.aget_state(thread_config(str(session_id)))
        return SessionResponse(
            session_id=session_id,
            document_id=UUID(session["document_id"]) if session.get("document_id") else None,
            created_at=session["created_at"],
            updated_at=session["updated_at"],
            turn_count=len(session["turns"]),
            turns=session["turns"],
            checkpoint_saved=bool(snapshot and snapshot.values),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Session read failed: session_id=%s", session_id)
        raise HTTPException(status_code=503, detail="Session memory unavailable.") from exc
